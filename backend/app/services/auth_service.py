"""Registration, login, token issuing/rotation, logout and password changes."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.exceptions import AuthenticationError, BadRequestError, ConflictError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    password_needs_rehash,
    verify_dummy_password,
    verify_password,
)
from app.models import RefreshToken, User
from app.schemas.auth import RegisterRequest, TokenResponse

logger = logging.getLogger(__name__)

INVALID_CREDENTIALS = "Invalid email or password."

# Argon2 deliberately takes ~50 ms of CPU. Running it in a worker thread keeps the
# async event loop free to serve other requests meanwhile.


async def _hash(password: str) -> str:
    return await run_in_threadpool(hash_password, password)


async def _verify(password: str, password_hash: str) -> bool:
    return await run_in_threadpool(verify_password, password, password_hash)


def _utcnow() -> datetime:
    return datetime.now(UTC)


# ---------- Registration & login ----------


async def register_user(session: AsyncSession, data: RegisterRequest) -> User:
    if await session.scalar(select(User.id).where(User.email == data.email)):
        raise ConflictError("An account with this email already exists.")

    user = User(
        email=data.email,
        password_hash=await _hash(data.password),
        full_name=data.full_name,
    )
    session.add(user)
    try:
        await session.commit()
    except IntegrityError as exc:  # two simultaneous registrations with the same email
        await session.rollback()
        raise ConflictError("An account with this email already exists.") from exc
    return user


async def authenticate(session: AsyncSession, email: str, password: str) -> User:
    user = await session.scalar(select(User).where(User.email == email))
    if user is None:
        await run_in_threadpool(verify_dummy_password, password)  # equalize timing
        raise AuthenticationError(INVALID_CREDENTIALS)
    if not await _verify(password, user.password_hash):
        raise AuthenticationError(INVALID_CREDENTIALS)
    if not user.is_active:
        raise AuthenticationError("This account is disabled.")

    # Transparently upgrade hashes created with older/weaker parameters.
    if password_needs_rehash(user.password_hash):
        user.password_hash = await _hash(password)
        await session.commit()
    return user


# ---------- Tokens ----------


def _new_refresh_record(
    user_id: uuid.UUID, family_id: uuid.UUID, settings: Settings
) -> tuple[str, RefreshToken]:
    raw = generate_refresh_token()
    record = RefreshToken(
        user_id=user_id,
        family_id=family_id,
        token_hash=hash_token(raw),
        expires_at=_utcnow() + timedelta(days=settings.refresh_token_expire_days),
    )
    return raw, record


def _token_response(user_id: uuid.UUID, raw_refresh: str, settings: Settings) -> TokenResponse:
    access_token, expires_in = create_access_token(user_id, settings)
    return TokenResponse(
        access_token=access_token, refresh_token=raw_refresh, expires_in=expires_in
    )


async def issue_tokens(session: AsyncSession, user: User, settings: Settings) -> TokenResponse:
    """Start a new session (token family) for a freshly logged-in user."""
    raw, record = _new_refresh_record(user.id, uuid.uuid4(), settings)
    session.add(record)
    await session.commit()
    return _token_response(user.id, raw, settings)


async def _revoke_family(session: AsyncSession, family_id: uuid.UUID) -> None:
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )


async def rotate_refresh_token(
    session: AsyncSession, raw_token: str, settings: Settings
) -> TokenResponse:
    """Exchange a refresh token for a new pair. The presented token becomes unusable."""
    # FOR UPDATE locks the row so two concurrent refreshes with the same token are
    # processed one after the other (the second one then sees it as already used).
    stored = await session.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == hash_token(raw_token))
        .with_for_update()
    )
    if stored is None:
        raise AuthenticationError("Invalid refresh token.")

    if stored.revoked_at is not None:
        # Reuse of a consumed token => it was copied. Kill the whole session.
        logger.warning(
            "Refresh token reuse detected; revoking family %s (user %s)",
            stored.family_id,
            stored.user_id,
        )
        await _revoke_family(session, stored.family_id)
        await session.commit()  # must persist before raising (errors roll back)
        raise AuthenticationError("Refresh token has been revoked.")

    if stored.expires_at <= _utcnow():
        raise AuthenticationError("Refresh token has expired.")

    user = await session.get(User, stored.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid refresh token.")

    raw, replacement = _new_refresh_record(user.id, stored.family_id, settings)
    session.add(replacement)
    await session.flush()  # assigns replacement.id
    stored.revoked_at = _utcnow()
    stored.replaced_by_id = replacement.id
    await session.commit()
    return _token_response(user.id, raw, settings)


async def logout(session: AsyncSession, raw_token: str) -> None:
    """Revoke the session the token belongs to. Silent if the token is unknown."""
    stored = await session.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw_token))
    )
    if stored is not None:
        await _revoke_family(session, stored.family_id)
        await session.commit()


# ---------- Account ----------


async def change_password(
    session: AsyncSession, user: User, current_password: str, new_password: str
) -> None:
    if not await _verify(current_password, user.password_hash):
        raise BadRequestError("Current password is incorrect.")

    user.password_hash = await _hash(new_password)
    # Sign out every session: a password change is often a response to compromise.
    await session.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_utcnow())
    )
    await session.commit()


# ---------- Housekeeping ----------


async def purge_expired_refresh_tokens(session: AsyncSession, *, grace_days: int = 7) -> int:
    """Delete token families whose NEWEST token expired more than `grace_days` ago.

    Whole families only: a live family keeps its consumed (revoked) tokens, because
    those are exactly what reuse detection needs to recognise a stolen copy.
    Returns the number of rows deleted.
    """
    cutoff = _utcnow() - timedelta(days=grace_days)
    dead_families = (
        select(RefreshToken.family_id)
        .group_by(RefreshToken.family_id)
        .having(func.max(RefreshToken.expires_at) < cutoff)
    )
    result = await session.execute(
        delete(RefreshToken).where(RefreshToken.family_id.in_(dead_families))
    )
    await session.commit()
    return result.rowcount or 0
