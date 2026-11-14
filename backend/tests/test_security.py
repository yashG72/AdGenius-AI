"""Unit tests for password hashing and token helpers (no database)."""

import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.models import MembershipRole

settings = get_settings()


def test_password_hash_roundtrip() -> None:
    hashed = hash_password("s3cret-password")

    assert hashed.startswith("$argon2id$")
    assert "s3cret-password" not in hashed
    assert verify_password("s3cret-password", hashed)
    assert not verify_password("wrong-password", hashed)


def test_same_password_hashes_differently() -> None:
    assert hash_password("same") != hash_password("same")  # random salt


def test_verify_against_garbage_hash_is_false() -> None:
    assert not verify_password("anything", "not-a-hash")


def test_access_token_roundtrip() -> None:
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id, settings)

    assert decode_access_token(token, settings) == user_id
    assert expires_in == settings.access_token_expire_minutes * 60


def test_expired_access_token_rejected() -> None:
    token, _ = create_access_token(uuid.uuid4(), settings, expires_delta=timedelta(seconds=-1))

    with pytest.raises(AuthenticationError):
        decode_access_token(token, settings)


def test_token_signed_with_other_key_rejected() -> None:
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": 0, "exp": 9999999999},
        "attacker-controlled-key-that-is-long-enough",
        algorithm="HS256",
    )

    with pytest.raises(AuthenticationError):
        decode_access_token(forged, settings)


def test_unsigned_alg_none_token_rejected() -> None:
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "type": "access", "iat": 0, "exp": 9999999999},
        key=None,
        algorithm="none",
    )

    with pytest.raises(AuthenticationError):
        decode_access_token(forged, settings)


def test_refresh_tokens_are_random_and_hash_is_stable() -> None:
    a, b = generate_refresh_token(), generate_refresh_token()

    assert a != b
    assert hash_token(a) == hash_token(a)
    assert len(hash_token(a)) == 64


def test_role_hierarchy() -> None:
    assert MembershipRole.OWNER.at_least(MembershipRole.ADMIN)
    assert MembershipRole.ADMIN.at_least(MembershipRole.ADMIN)
    assert not MembershipRole.MEMBER.at_least(MembershipRole.ADMIN)
