"""Low-level security primitives: password hashing, access tokens, refresh tokens.

No database access here - just pure functions, so they are easy to test in isolation.

Two kinds of tokens:
- Access token: a signed JWT, valid ~15 min, sent on every request. Stateless: the
  server verifies the signature and never stores it.
- Refresh token: a long random string, valid ~30 days, used only to obtain new tokens.
  Stored server-side (as a hash) so it can be revoked and rotated.
"""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.core.config import Settings
from app.core.exceptions import AuthenticationError

# ---------- Passwords ----------

# Argon2id: memory-hard hashing (resistant to GPU cracking). Each hash embeds its own
# random salt and parameters, so the stored string is all that's needed to verify.
_password_hasher = PasswordHasher()

# Used to spend the same time on "unknown email" as on "wrong password", so response
# timing does not reveal which emails are registered.
_DUMMY_HASH = _password_hasher.hash("timing-equalization-dummy")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def verify_dummy_password(password: str) -> None:
    verify_password(password, _DUMMY_HASH)


def password_needs_rehash(password_hash: str) -> bool:
    """True if the hash used weaker parameters than today's defaults."""
    return _password_hasher.check_needs_rehash(password_hash)


# ---------- Access tokens (JWT) ----------

ACCESS_TOKEN_TYPE = "access"


def create_access_token(
    user_id: uuid.UUID, settings: Settings, expires_delta: timedelta | None = None
) -> tuple[str, int]:
    """Return (token, lifetime_in_seconds)."""
    lifetime = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + lifetime,
        "jti": uuid.uuid4().hex,  # unique token id (useful for logging / future denylist)
    }
    token = jwt.encode(
        payload, settings.jwt_secret_key.get_secret_value(), algorithm=settings.jwt_algorithm
    )
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Verify signature + expiry and return the user ID. Raises AuthenticationError."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key.get_secret_value(),
            # Pin the algorithm: never trust the "alg" header sent by the client.
            algorithms=[settings.jwt_algorithm],
            options={"require": ["exp", "iat", "sub"]},
        )
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise AuthenticationError("Invalid or expired token.")
        return uuid.UUID(payload["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired token.") from exc


# ---------- Refresh tokens (opaque) ----------


def generate_refresh_token() -> str:
    """384 bits of randomness - unguessable, so a fast hash is enough to store it."""
    return secrets.token_urlsafe(48)


def hash_token(token: str) -> str:
    """SHA-256 hex digest. The database only ever sees this, never the raw token."""
    return hashlib.sha256(token.encode()).hexdigest()
