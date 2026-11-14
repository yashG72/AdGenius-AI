"""Search-result cache (Redis), so repeated research doesn't re-spend API credits.

Cached results keep their ORIGINAL retrieval timestamp - a cache hit is honest about
when the evidence was actually fetched. If Redis is unavailable the cache simply
behaves as a miss; research still works, it just costs more credits.
"""

import hashlib
import json
import logging
import time
from functools import lru_cache
from typing import Any, Protocol

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)

CACHE_PREFIX = "websearch:v1:"


def cache_key(provider: str, query: str, params: dict[str, Any]) -> str:
    normalized = " ".join(query.lower().split())
    payload = json.dumps({"p": provider, "q": normalized, **params}, sort_keys=True, default=str)
    return CACHE_PREFIX + hashlib.sha256(payload.encode()).hexdigest()


class SearchCache(Protocol):
    async def get(self, key: str) -> list[Any] | None: ...
    async def set(self, key: str, value: list[Any], ttl_seconds: int) -> None: ...


class RedisSearchCache:
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def get(self, key: str) -> list[Any] | None:
        try:
            raw = await self._client.get(key)
        except Exception as exc:  # cache must never break research
            logger.warning("Search cache read failed (%s); treating as miss", type(exc).__name__)
            return None
        return json.loads(raw) if raw else None

    async def set(self, key: str, value: list[Any], ttl_seconds: int) -> None:
        if ttl_seconds <= 0:
            return
        try:
            await self._client.set(key, json.dumps(value), ex=ttl_seconds)
        except Exception as exc:
            logger.warning("Search cache write failed (%s)", type(exc).__name__)


class InMemorySearchCache:
    """Process-local cache (tests, or running without Redis)."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, list[Any]]] = {}

    async def get(self, key: str) -> list[Any] | None:
        entry = self._store.get(key)
        if entry is None or entry[0] < time.monotonic():
            return None
        return entry[1]

    async def set(self, key: str, value: list[Any], ttl_seconds: int) -> None:
        if ttl_seconds > 0:
            self._store[key] = (time.monotonic() + ttl_seconds, value)


@lru_cache
def get_redis() -> redis.Redis:
    """Shared async Redis client for the API process (closed on app shutdown)."""
    settings = get_settings()
    return redis.from_url(settings.redis_url, socket_connect_timeout=2, socket_timeout=5)
