"""Rate limiting (Redis fixed-window counters).

Why: logins can be brute-forced, and several endpoints spend real money or CPU per call
(LLM answers, web research, campaign runs, document embedding). Every limit is a named
`Limit` so policies live in one place and show up in error messages.

How: one Redis key per (limit, subject, window). A tiny Lua script increments it and
sets the expiry atomically, so concurrent requests can never slip past the counter.

Failure mode: if Redis is unreachable the limiter FAILS OPEN (allows the request and
logs a warning). Locking every user out because a cache is down is the worse outcome
for this app; production alerting should watch for the warning.
"""

import hashlib
import logging
import math
import time
from dataclasses import dataclass
from typing import Protocol

import redis.asyncio as redis

logger = logging.getLogger(__name__)

KEY_PREFIX = "ratelimit:v1:"

# KEYS[1] = counter key, ARGV[1] = window in ms, ARGV[2] = amount to add (0 = peek)
# Returns {count, ms until the window resets}.
_HIT_SCRIPT = """
local count
if tonumber(ARGV[2]) > 0 then
  count = redis.call('INCRBY', KEYS[1], ARGV[2])
  if count == tonumber(ARGV[2]) then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
  end
else
  count = tonumber(redis.call('GET', KEYS[1]) or '0')
end
local ttl = redis.call('PTTL', KEYS[1])
if ttl < 0 then ttl = tonumber(ARGV[1]) end
return {count, ttl}
"""


@dataclass(frozen=True)
class Limit:
    """`requests` allowed per `window_seconds` for one subject (an IP, user or email)."""

    name: str
    requests: int
    window_seconds: int


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    count: int
    limit: int
    retry_after: int  # seconds until the window resets (>= 1 when blocked)


class RateLimiter(Protocol):
    async def hit(self, limit: Limit, subject: str, amount: int = 1) -> RateLimitResult: ...
    async def peek(self, limit: Limit, subject: str) -> RateLimitResult: ...
    async def reset(self, limit: Limit, subject: str) -> None: ...


def _key(limit: Limit, subject: str) -> str:
    # Hash the subject: keys never contain raw emails/IPs, and length stays bounded.
    digest = hashlib.sha256(subject.lower().encode()).hexdigest()[:32]
    return f"{KEY_PREFIX}{limit.name}:{digest}"


def _result(limit: Limit, count: int, ttl_ms: int) -> RateLimitResult:
    return RateLimitResult(
        allowed=count <= limit.requests,
        count=count,
        limit=limit.requests,
        retry_after=max(1, math.ceil(ttl_ms / 1000)),
    )


class RedisRateLimiter:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client
        self._script = client.register_script(_HIT_SCRIPT)

    async def _run(self, limit: Limit, subject: str, amount: int) -> RateLimitResult:
        try:
            count, ttl_ms = await self._script(
                keys=[_key(limit, subject)], args=[limit.window_seconds * 1000, amount]
            )
        except Exception as exc:  # fail open - see module docstring
            logger.warning("Rate limiter unavailable (%s); allowing request", type(exc).__name__)
            return RateLimitResult(True, 0, limit.requests, 0)
        return _result(limit, int(count), int(ttl_ms))

    async def hit(self, limit: Limit, subject: str, amount: int = 1) -> RateLimitResult:
        return await self._run(limit, subject, amount)

    async def peek(self, limit: Limit, subject: str) -> RateLimitResult:
        return await self._run(limit, subject, 0)

    async def reset(self, limit: Limit, subject: str) -> None:
        try:
            await self._client.delete(_key(limit, subject))
        except Exception as exc:
            logger.warning("Rate limiter reset failed (%s)", type(exc).__name__)


class InMemoryRateLimiter:
    """Process-local limiter with the same semantics (tests, or running without Redis)."""

    def __init__(self) -> None:
        self._windows: dict[str, tuple[float, int]] = {}  # key -> (resets_at, count)

    def _run(self, limit: Limit, subject: str, amount: int) -> RateLimitResult:
        key, now = _key(limit, subject), time.monotonic()
        resets_at, count = self._windows.get(key, (0.0, 0))
        if resets_at <= now:
            resets_at, count = now + limit.window_seconds, 0
        count += amount
        if amount:
            self._windows[key] = (resets_at, count)
        return _result(limit, count, int((resets_at - now) * 1000))

    async def hit(self, limit: Limit, subject: str, amount: int = 1) -> RateLimitResult:
        return self._run(limit, subject, amount)

    async def peek(self, limit: Limit, subject: str) -> RateLimitResult:
        return self._run(limit, subject, 0)

    async def reset(self, limit: Limit, subject: str) -> None:
        self._windows.pop(_key(limit, subject), None)
