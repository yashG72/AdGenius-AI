"""Rate-limit policies and the FastAPI dependencies that enforce them.

Subjects:
- anonymous auth endpoints are limited per client IP (real IP via trusted proxies);
- logged-in, expensive endpoints are limited per user (a user can't dodge it by
  switching networks, and colleagues behind one office IP don't share a budget);
- failed logins are additionally counted per EMAIL, so a distributed attack on one
  account is still stopped (see auth_service / routes.auth).
"""

import ipaddress
from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.api.deps import CurrentUserDep, SettingsDep
from app.core.config import Settings, get_settings
from app.core.exceptions import RateLimitedError
from app.core.rate_limit import InMemoryRateLimiter, Limit, RateLimiter, RedisRateLimiter
from app.research.cache import get_redis

# ---------- Policies (one place to tune them) ----------

# Anonymous / per IP
LOGIN_PER_IP = Limit("login-ip", 30, 15 * 60)
REGISTER_PER_IP = Limit("register-ip", 10, 60 * 60)
REFRESH_PER_IP = Limit("refresh-ip", 120, 15 * 60)
DEMO_LOGIN_PER_IP = Limit("demo-login-ip", 30, 15 * 60)  # each click issues a session

# Expensive / per user
KNOWLEDGE_SEARCH = Limit("knowledge-search", 60, 60)  # local embeddings, cheap-ish
KNOWLEDGE_ASK = Limit("knowledge-ask", 20, 60)  # LLM call per request
WEB_RESEARCH = Limit("web-research", 10, 60 * 60)  # several Tavily credits + LLM
CAMPAIGN_RUNS = Limit("campaign-runs", 20, 60 * 60)  # ~10 LLM calls + research each
DOCUMENT_UPLOADS = Limit("document-uploads", 60, 60 * 60)  # embedding CPU + storage
PASSWORD_CHANGE = Limit("password-change", 5, 15 * 60)  # verifies the current password


# ---------- Limiter + client IP ----------


# Used when Redis isn't configured: correct for ONE API instance (free hosting).
_memory_limiter = InMemoryRateLimiter()


def get_rate_limiter() -> RateLimiter:
    """Redis-backed limiter (shared by every API process). Tests override this."""
    if not get_settings().redis_url:
        return _memory_limiter
    return RedisRateLimiter(get_redis())


RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]


def _is_trusted(host: str, trusted: list[str]) -> bool:
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(address in ipaddress.ip_network(net, strict=False) for net in trusted)


def client_ip(request: Request, settings: Settings) -> str:
    """The real client address.

    X-Forwarded-For can be forged by anyone, so it is only believed when the direct
    peer is a trusted proxy. We walk the list right-to-left (each proxy appends the
    address it saw) and stop at the first address that is not one of our proxies.
    """
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted(peer, settings.trusted_proxies):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    for hop in reversed([h.strip() for h in forwarded.split(",") if h.strip()]):
        if not _is_trusted(hop, settings.trusted_proxies):
            return hop
    return peer


async def enforce(limiter: RateLimiter, limit: Limit, subject: str, settings: Settings) -> None:
    if not settings.rate_limit_enabled:
        return
    result = await limiter.hit(limit, subject)
    if not result.allowed:
        raise RateLimitedError(
            f"Too many requests - try again in {humanize_seconds(result.retry_after)}.",
            retry_after=result.retry_after,
            details={"limit": limit.name, "max_requests": limit.requests},
        )


def humanize_seconds(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{round(seconds / 60)} minutes"


# ---------- Dependency factories ----------


def limit_by_ip(limit: Limit) -> Callable[..., Awaitable[None]]:
    async def dependency(request: Request, settings: SettingsDep, limiter: RateLimiterDep) -> None:
        await enforce(limiter, limit, client_ip(request, settings), settings)

    return dependency


def limit_by_user(limit: Limit) -> Callable[..., Awaitable[None]]:
    async def dependency(
        user: CurrentUserDep, settings: SettingsDep, limiter: RateLimiterDep
    ) -> None:
        await enforce(limiter, limit, str(user.id), settings)

    return dependency
