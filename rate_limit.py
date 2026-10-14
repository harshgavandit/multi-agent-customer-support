"""Atomic fixed-window admission via the Upstash Redis REST API.

Only hashed session identifiers and expiring counters are stored in Redis.
Redis failures block requests so an outage cannot silently bypass limits.
"""
import hashlib
import math

import requests

import config
from errors import RateLimitExceeded, RateLimitUnavailable

_SCRIPT = """
local count = tonumber(redis.call('GET', KEYS[1]) or '0')
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then
    redis.call('SET', KEYS[1], 0, 'PX', ARGV[2])
    count = 0
    ttl = tonumber(ARGV[2])
end
if count >= tonumber(ARGV[1]) then
    return {0, 0, ttl}
end
count = redis.call('INCR', KEYS[1])
return {1, tonumber(ARGV[1]) - count, ttl}
"""


def redis_command(command: list):
    """No credentials in URLs, exceptions or logs; do not follow redirects."""
    if config.configuration_problems():
        raise RateLimitUnavailable()
    try:
        response = requests.post(
            config.UPSTASH_REDIS_REST_URL,
            headers={"Authorization": f"Bearer {config.UPSTASH_REDIS_REST_TOKEN}"},
            json=command,
            timeout=10,
            allow_redirects=False,
        )
        if response.status_code != 200:
            raise ValueError("Redis rejected the request")
        payload = response.json()
        if not isinstance(payload, dict) or "error" in payload or "result" not in payload:
            raise ValueError("Invalid Redis response")
        return payload["result"]
    except (requests.RequestException, ValueError):
        raise RateLimitUnavailable() from None


def consume(scope: str, identity: str, limit: int, window_seconds: int) -> dict:
    if not config.RATE_LIMIT_ENABLED:
        return {"allowed": True, "remaining": limit, "retry_after_seconds": 0}
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    key = f"{config.RATE_LIMIT_PREFIX}:rate-limit:{scope}:{digest}"
    result = redis_command(["EVAL", _SCRIPT, 1, key, limit, window_seconds * 1000])
    if not isinstance(result, list) or len(result) != 3 or any(type(v) is not int for v in result):
        raise RateLimitUnavailable()
    allowed, remaining, ttl = result
    if allowed not in (0, 1) or not 0 <= remaining < limit or not 0 < ttl <= window_seconds * 1000:
        raise RateLimitUnavailable()
    retry_after = max(1, math.ceil(ttl / 1000))
    if not allowed:
        raise RateLimitExceeded(retry_after)
    return {"allowed": True, "remaining": remaining, "retry_after_seconds": retry_after}


def check_customer_turn(session_id: str) -> dict:
    return consume("session", session_id, config.RATE_LIMIT_REQUESTS, config.RATE_LIMIT_WINDOW_SECONDS)


def check_model_call() -> dict:
    # Shared across every session: New Session cannot bypass the model budget.
    return consume("model", config.LLM_MODEL, config.LLM_RATE_LIMIT_REQUESTS, config.RATE_LIMIT_WINDOW_SECONDS)
