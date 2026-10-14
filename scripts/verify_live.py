"""Real-service verification. Uses small model requests and isolated Redis keys.

Run from the project root: python -m scripts.verify_live
The report contains no credentials or customer transcripts.
"""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import config
from errors import RateLimitExceeded, SupportError
from llm.client import complete_json
from pipeline.graph import run_customer_turn
from pipeline.approval_graph import resolve_approval
from rate_limit import consume, redis_command, check_model_call
from session import session_store as store


checks = []
run_id = uuid.uuid4().hex


def record(name, operation):
    started = time.monotonic()
    try:
        details = operation() or {}
        result = {'check': name, 'status': 'PASS', 'details': details}
    except SupportError as exc:
        result = {'check': name, 'status': 'FAIL', 'error': str(exc)}
    except Exception as exc:
        # Never serialize raw third-party exception text.
        result = {'check': name, 'status': 'FAIL', 'error_type': type(exc).__name__}
    result['duration_seconds'] = round(time.monotonic() - started, 3)
    checks.append(result)
    print(json.dumps(result), flush=True)
    return result['status'] == 'PASS'


def redis_ping():
    assert redis_command(['PING']) == 'PONG'
    return {'result': 'PONG'}


def rate_limit_boundary():
    identity = run_id + '-boundary'
    first = consume('verification', identity, 2, 2)
    second = consume('verification', identity, 2, 2)
    assert first['remaining'] == 1 and second['remaining'] == 0
    try:
        consume('verification', identity, 2, 2)
    except RateLimitExceeded as exc:
        assert 1 <= exc.retry_after_seconds <= 2
    else:
        raise AssertionError('Third request was not blocked')
    time.sleep(2.1)
    reset = consume('verification', identity, 2, 2)
    assert reset['remaining'] == 1
    return {'limit': 2, 'window_seconds': 2, 'third_request': 'blocked', 'after_expiry': 'allowed'}


def concurrent_rate_limit():
    identity = run_id + '-concurrent'
    def attempt(_):
        try:
            consume('verification', identity, 3, 10)
            return True
        except RateLimitExceeded:
            return False
    with ThreadPoolExecutor(max_workers=8) as pool:
        admitted = sum(pool.map(attempt, range(8)))
    assert admitted == 3
    return {'concurrent_requests': 8, 'allowed': admitted, 'blocked': 8 - admitted}


def model_json():
    assert complete_json('Return only a JSON object with ok set to true.', 'Verification: respond with JSON.') == {'ok': True}
    return {'model': config.LLM_MODEL, 'json_object': 'valid'}


def billing():
    sid = run_id + '-billing'
    first = run_customer_turn(sid, 'I have a problem with my order.')
    assert first['awaiting_clarification'] and len(first['conversation_history']) == 2
    final = run_customer_turn(sid, 'My order is ORD-1003. Please check the invoice amount and payment status for this order.')
    assert final['assigned_team'] == 'payments_team'
    assert final['tool_result']['invoice']['amount'] == 5600
    assert final['tool_result']['payment_status']['status'] == 'pending'
    assert store.get_or_create_session(sid)['turn_count'] == 2
    assert store.get_or_create_session(sid + '-new')['conversation_history'] == []
    return {'clarification': 'passed', 'team': 'payments_team', 'amount': 5600, 'payment': 'pending', 'resume_and_isolation': 'passed'}


def refund(decision):
    sid = run_id + '-refund-' + decision
    final = run_customer_turn(sid, 'I want a refund of 2200 rupees for my order ORD-1006 because the Bluetooth speaker is defective.')
    assert final['assigned_team'] == 'refunds_team'
    pending = [r for r in store.list_pending_approvals() if r['session_id'] == sid]
    assert len(pending) == 1 and pending[0]['refund_amount'] == 2200
    if decision == 'approved':
        run_customer_turn(sid, 'Please give me an update on the same refund of 2200 rupees for ORD-1006.')
        assert len([r for r in store.list_pending_approvals() if r['session_id'] == sid]) == 1
    resolve_approval(pending[0]['approval_id'], decision)
    resolved = store.get_pending_approval(pending[0]['approval_id'])
    assert resolved['status'] == decision and resolved['resolved_at'] is not None
    text = store.get_or_create_session(sid)['conversation_history'][-1]['content']
    assert ('been approved' if decision == 'approved' else 'unable to approve') in text
    try:
        resolve_approval(pending[0]['approval_id'], decision)
    except SupportError:
        pass
    else:
        raise AssertionError('Repeated approval succeeded')
    return {'decision': decision, 'pending_record': 'created', 'outcome_in_resumed_chat': True, 'repeated_decision': 'blocked'}


def ineligible():
    sid = run_id + '-ineligible'
    final = run_customer_turn(sid, 'I want a refund of 12000 rupees for order ORD-1005 because the espresso machine is damaged.')
    assert final['assigned_team'] == 'refunds_team'
    assert "isn't eligible" in final['conversation_history'][-1]['content']
    assert not any(r['session_id'] == sid for r in store.list_pending_approvals())
    return {'order': 'ORD-1005', 'eligibility': 'rejected', 'approval_created': False}


def general_support():
    final = run_customer_turn(run_id + '-general', 'The mobile app crashes immediately on opening the settings screen on my Android phone, even after reinstalling. This is a technical issue, unrelated to orders or payments.')
    assert final['assigned_team'] == 'unassigned'
    assert final['tool_calls'] == []
    return {'team': 'unassigned', 'reply': 'present'}


def application_admission():
    # Real Redis and the real graph entry point; blocking happens before model calls.
    sid = run_id + '-blocked'
    with patch.object(config, 'RATE_LIMIT_REQUESTS', 1):
        consume('session', sid, 1, config.RATE_LIMIT_WINDOW_SECONDS)
        try:
            run_customer_turn(sid, 'This request must be blocked.')
        except RateLimitExceeded:
            assert store.get_session(sid) is None
        else:
            raise AssertionError('Graph entry point did not block')
    return {'graph_entry': 'blocked', 'session_created': False, 'model_called': False}


def global_model_admission():
    # Prime the shared budget with real Redis; the next call must stop before
    # entering LiteLLM, regardless of which customer session invokes it.
    with patch.object(config, 'LLM_RATE_LIMIT_REQUESTS', 1):
        check_model_call()
        with patch('llm.client.litellm.completion') as provider:
            try:
                complete_json('Return JSON.', 'This request must be blocked.')
            except RateLimitExceeded:
                provider.assert_not_called()
            else:
                raise AssertionError('Shared model budget was bypassed')
    return {'shared_model_budget': 'blocked', 'provider_called': False}


def main():
    if config.configuration_problems():
        raise SystemExit('Configuration is incomplete; run the app for safe setup messages.')
    if not config.RATE_LIMIT_ENABLED:
        raise SystemExit('RATE_LIMIT_ENABLED must be true for real-service verification.')
    with patch.object(config, 'RATE_LIMIT_PREFIX', config.RATE_LIMIT_PREFIX + ':verify:' + run_id):
        redis_ok = record('redis_ping', redis_ping)
        if redis_ok:
            record('redis_limit_and_expiry', rate_limit_boundary)
            record('redis_concurrent_admission', concurrent_rate_limit)
            record('application_rate_limit_admission', application_admission)
            with patch.object(config, 'RATE_LIMIT_PREFIX', config.RATE_LIMIT_PREFIX + ':global-admission'):
                record('global_model_rate_limit_admission', global_model_admission)
        model_ok = record('real_model_json_completion', model_json)
        if model_ok:
            record('multi_turn_billing_resume_isolation', billing)
            record('refund_approval_and_duplicate_protection', lambda: refund('approved'))
            record('refund_denial', lambda: refund('denied'))
            record('ineligible_refund', ineligible)
            record('general_support', general_support)
    report = {'verified_at_utc': datetime.now(timezone.utc).isoformat(), 'model': config.LLM_MODEL,
              'checks': checks, 'passed': sum(c['status'] == 'PASS' for c in checks),
              'failed': sum(c['status'] == 'FAIL' for c in checks),
              'scope': 'Real Upstash and real model; simulated SQLite reference orders and in-memory approvals; no actual payment processing.'}
    Path('verification').mkdir(exist_ok=True)
    Path('verification/live_checks.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    raise SystemExit(1 if report['failed'] else 0)


if __name__ == '__main__':
    main()
