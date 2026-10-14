import json
import sqlite3
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import patch

import config
import rate_limit
from errors import ModelUnavailable, RateLimitExceeded, RateLimitUnavailable, SupportError
from llm.client import complete_json
from pipeline import compaction, info_gathering
from pipeline.approval_graph import resolve_approval
from pipeline.graph import run_customer_turn
from pipeline.state import CompactedTicketInfo, new_session_state
from session import session_store as store
from tools.mock_tools import lookup_invoice, check_payment_status, check_refund_eligibility
from db.connection import get_read_only_connection


def ticket(category='refund_request', order='ORD-1006', amount=2200):
    return dict(issue_summary='Customer requests assistance.', issue_category=category,
                order_id=order, refund_amount=amount if category == 'refund_request' else None,
                customer_sentiment='neutral', info_complete=True, missing_fields=[])


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.session = 'test-' + uuid.uuid4().hex
        self.admission = patch('pipeline.graph.check_customer_turn')
        self.admission.start()
        self.addCleanup(self.admission.stop)

    def turn(self, details=None, message='Please help with my order.'):
        with patch.object(info_gathering, 'complete_json', return_value={'info_complete': True}), patch.object(compaction, 'complete_json', return_value=details or ticket()):
            return run_customer_turn(self.session, message)

    def test_billing_routes_and_reads_actual_db(self):
        state = self.turn(ticket('billing_issue', 'ord-1003'))
        self.assertEqual(state['assigned_team'], 'payments_team')
        self.assertEqual(state['tool_result']['invoice']['amount'], 5600)
        self.assertEqual(state['tool_result']['payment_status']['status'], 'pending')

    def test_clarification_stops_before_compaction(self):
        with patch.object(info_gathering, 'complete_json', return_value={'info_complete': False, 'clarifying_question': 'Which order?'}), patch.object(compaction, 'complete_json') as compact:
            state = run_customer_turn(self.session, 'Help')
        compact.assert_not_called()
        self.assertTrue(state['awaiting_clarification'])
        self.assertEqual(state['conversation_history'][-1]['content'], 'Which order?')

    def test_refund_is_pending_then_approved_and_resumable(self):
        self.turn()
        record = next(r for r in store.list_pending_approvals() if r['session_id'] == self.session)
        resolve_approval(record['approval_id'], 'approved')
        state = store.get_session(self.session)
        self.assertIn('approved', state['conversation_history'][-1]['content'])
        self.assertEqual(store.get_pending_approval(record['approval_id'])['status'], 'approved')
        self.assertEqual(store.get_or_create_session(self.session), state)

    def test_denial_delivers_outcome(self):
        self.turn()
        record = next(r for r in store.list_pending_approvals() if r['session_id'] == self.session)
        resolve_approval(record['approval_id'], 'denied')
        self.assertIn('unable to approve', store.get_session(self.session)['conversation_history'][-1]['content'])

    def test_ineligible_and_unknown_orders_never_queue(self):
        for order in ('ORD-1005', 'ORD-1011', 'ORD-9999'):
            self.turn(ticket(order=order))
        self.assertFalse(any(r['session_id'] == self.session for r in store.list_pending_approvals()))

    def test_unknown_billing_order(self):
        state = self.turn(ticket('billing_issue', 'ORD-9999'))
        self.assertIn("couldn't find", state['conversation_history'][-1]['content'])

    def test_duplicate_pending_request_is_not_created(self):
        self.turn()
        self.turn(message='Any update?')
        records = [r for r in store.list_pending_approvals() if r['session_id'] == self.session]
        self.assertEqual(len(records), 1)
        self.assertIn('already under', store.get_session(self.session)['conversation_history'][-1]['content'])

    def test_concurrent_approval_decisions_append_once(self):
        self.turn()
        record = next(r for r in store.list_pending_approvals() if r['session_id'] == self.session)
        def decide(decision):
            try:
                resolve_approval(record['approval_id'], decision)
                return True
            except SupportError:
                return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(decide, ['approved', 'denied']))
        self.assertEqual(sum(results), 1)
        self.assertEqual(len(store.get_session(self.session)['conversation_history']), 3)

    def test_repeated_and_invalid_decisions_are_rejected(self):
        self.turn()
        record = next(r for r in store.list_pending_approvals() if r['session_id'] == self.session)
        with self.assertRaises(SupportError):
            resolve_approval(record['approval_id'], 'invalid')
        resolve_approval(record['approval_id'], 'approved')
        with self.assertRaises(SupportError):
            resolve_approval(record['approval_id'], 'approved')

    def test_failed_compaction_does_not_mutate_session(self):
        self.turn(ticket('billing_issue', 'ORD-1003'))
        before = store.get_session(self.session)
        with patch.object(info_gathering, 'complete_json', return_value={'info_complete': True}), patch.object(compaction, 'complete_json', side_effect=ModelUnavailable('Failed')):
            with self.assertRaises(ModelUnavailable):
                run_customer_turn(self.session, 'Another message')
        self.assertEqual(store.get_session(self.session), before)

    def test_failed_admission_does_not_create_session_or_call_model(self):
        with patch('pipeline.graph.check_customer_turn', side_effect=RateLimitExceeded(12)), patch.object(info_gathering, 'complete_json') as model:
            with self.assertRaises(RateLimitExceeded):
                run_customer_turn(self.session, 'Help')
        model.assert_not_called()
        self.assertIsNone(store.get_session(self.session))

    def test_model_boolean_string_is_rejected(self):
        with patch.object(info_gathering, 'complete_json', return_value={'info_complete': 'false'}):
            with self.assertRaises(ModelUnavailable):
                run_customer_turn(self.session, 'Help')
        self.assertEqual(store.get_session(self.session)['turn_count'], 0)

    def test_invalid_refund_amounts_and_missing_details_are_rejected(self):
        for amount in (-1, 0, float('nan'), float('inf'), None):
            with self.subTest(amount=amount):
                with self.assertRaises(ModelUnavailable):
                    self.turn(ticket(amount=amount))
        with self.assertRaises(ModelUnavailable):
            self.turn(ticket(order=None))
        self.assertFalse(any(r['session_id'] == self.session for r in store.list_pending_approvals()))

    def test_incomplete_compaction_cannot_reach_tools(self):
        details = ticket()
        details['info_complete'] = False
        details['missing_fields'] = ['order_id']
        with self.assertRaises(ModelUnavailable):
            self.turn(details)

    def test_general_support_routes(self):
        state = self.turn(ticket('technical_issue', None))
        self.assertEqual(state['assigned_team'], 'unassigned')
        self.assertEqual(state['tool_calls'], [])

    def test_sessions_are_isolated_and_read_copies_cannot_mutate_storage(self):
        self.turn()
        state = store.get_session(self.session)
        state['conversation_history'].clear()
        self.assertEqual(len(store.get_session(self.session)['conversation_history']), 2)
        self.assertEqual(store.get_or_create_session(self.session + '-new')['conversation_history'], [])
        approval = next(r for r in store.list_pending_approvals() if r['session_id'] == self.session)
        approval['status'] = 'approved'
        self.assertEqual(store.get_pending_approval(approval['approval_id'])['status'], 'pending')

    def test_empty_and_oversized_input_rejected(self):
        for message in (' ', 'x' * 8001):
            with self.assertRaises(SupportError):
                run_customer_turn(self.session, message)


class RateLimitTests(unittest.TestCase):
    def test_admitted_request_hashes_identity_and_sets_window(self):
        with patch.object(config, 'RATE_LIMIT_ENABLED', True), patch.object(rate_limit, 'redis_command', return_value=[1, 2, 2500]) as redis:
            result = rate_limit.consume('session', 'private-session', 3, 3)
        self.assertEqual(result['remaining'], 2)
        self.assertEqual(result['retry_after_seconds'], 3)
        command = redis.call_args.args[0]
        self.assertEqual(command[0], 'EVAL')
        self.assertNotIn('private-session', command[3])
        self.assertEqual(command[-1], 3000)

    def test_denied_request_carries_retry_after(self):
        with patch.object(config, 'RATE_LIMIT_ENABLED', True), patch.object(rate_limit, 'redis_command', return_value=[0, 0, 1200]):
            with self.assertRaises(RateLimitExceeded) as context:
                rate_limit.consume('session', 'id', 3, 3)
        self.assertEqual(context.exception.retry_after_seconds, 2)

    def test_invalid_redis_response_fails_closed(self):
        for result in (None, 'ok', [1], [1, 2, -1], [True, 2, 1000], [1, 3, 1000]):
            with self.subTest(result=result), patch.object(config, 'RATE_LIMIT_ENABLED', True), patch.object(rate_limit, 'redis_command', return_value=result):
                with self.assertRaises(RateLimitUnavailable):
                    rate_limit.consume('session', 'id', 3, 3)

    def test_disabled_limiter_never_contacts_redis(self):
        with patch.object(config, 'RATE_LIMIT_ENABLED', False), patch.object(rate_limit, 'redis_command') as redis:
            self.assertTrue(rate_limit.consume('session', 'id', 3, 3)['allowed'])
        redis.assert_not_called()

    def test_redis_http_failure_does_not_expose_secrets(self):
        response = SimpleNamespace(status_code=401)
        with patch.object(config, 'configuration_problems', return_value=[]), patch.object(rate_limit.requests, 'post', return_value=response) as post:
            with self.assertRaises(RateLimitUnavailable) as context:
                rate_limit.redis_command(['PING'])
        self.assertNotIn('Bearer', str(context.exception))
        if config.UPSTASH_REDIS_REST_TOKEN:
            self.assertNotIn(config.UPSTASH_REDIS_REST_TOKEN, str(context.exception))
        self.assertFalse(post.call_args.kwargs['allow_redirects'])

    def test_redis_json_error_and_timeout_fail_closed(self):
        response = SimpleNamespace(status_code=200, json=lambda: {'error': 'private-provider-error'})
        for options in ({'return_value':response}, {'side_effect':rate_limit.requests.Timeout('private-provider-error')}):
            with patch.object(config, 'configuration_problems', return_value=[]), patch.object(rate_limit.requests, 'post', **options):
                with self.assertRaises(RateLimitUnavailable) as context:
                    rate_limit.redis_command(['PING'])
                self.assertNotIn('private-provider-error', str(context.exception))

    def test_global_model_limit_uses_shared_identity(self):
        with patch.object(rate_limit, 'consume') as consume:
            rate_limit.check_model_call()
        self.assertEqual(consume.call_args.args[:2], ('model', config.LLM_MODEL))


class ModelTests(unittest.TestCase):
    def test_json_object_is_parsed(self):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"ok":true}'))])
        with patch('llm.client.check_model_call'), patch('llm.client.litellm.completion', return_value=response) as completion:
            self.assertEqual(complete_json('JSON', 'test'), {'ok': True})
        self.assertEqual(completion.call_args.kwargs['model'], config.LLM_MODEL)
        self.assertEqual(completion.call_args.kwargs['timeout'], config.LLM_TIMEOUT_SECONDS)

    def test_malformed_or_nonobject_json_rejected(self):
        for content in ('invalid', '[]', 'null', None):
            response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
            with patch('llm.client.check_model_call'), patch('llm.client.litellm.completion', return_value=response):
                with self.assertRaises(ModelUnavailable):
                    complete_json('JSON', 'test')

    def test_model_limit_blocks_provider_call(self):
        with patch('llm.client.check_model_call', side_effect=RateLimitExceeded(10)), patch('llm.client.litellm.completion') as completion:
            with self.assertRaises(RateLimitExceeded):
                complete_json('JSON', 'test')
        completion.assert_not_called()

    def test_provider_exception_is_redacted(self):
        with patch('llm.client.check_model_call'), patch('llm.client.litellm.completion', side_effect=RuntimeError('private-token')):
            with self.assertRaises(ModelUnavailable) as context:
                complete_json('JSON', 'test')
        self.assertNotIn('private-token', str(context.exception))


class DatabaseTests(unittest.TestCase):
    def test_reference_database_has_twelve_seeded_orders(self):
        conn = get_read_only_connection()
        try:
            self.assertEqual(conn.execute('SELECT COUNT(*) FROM orders').fetchone()[0], 12)
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("UPDATE invoices SET amount=0 WHERE order_id='ORD-1001'")
        finally:
            conn.close()

    def test_actual_tools_and_unknown_order(self):
        self.assertEqual(lookup_invoice('ORD-1006')['amount'], 2200)
        self.assertEqual(check_payment_status('ORD-1006')['status'], 'paid')
        self.assertTrue(check_refund_eligibility('ORD-1006')[0])
        self.assertFalse(check_refund_eligibility('ORD-1005')[0])
        self.assertFalse(lookup_invoice("' OR 1=1 --")['found'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
