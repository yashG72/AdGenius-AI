"""Auth API: registration, login, /me, refresh rotation, reuse detection, logout."""

import pytest
from httpx import AsyncClient

from tests.conftest import DEFAULT_PASSWORD

pytestmark = pytest.mark.anyio

API = "/api/v1/auth"


async def login(client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD) -> dict:
    response = await client.post(f"{API}/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


async def register(client: AsyncClient, email: str, password: str = DEFAULT_PASSWORD):
    return await client.post(
        f"{API}/register", json={"email": email, "password": password, "full_name": " Jane "}
    )


def bearer(tokens: dict) -> dict:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


# ---------- Registration ----------


async def test_register_creates_user(client: AsyncClient) -> None:
    response = await register(client, "Jane@Example.COM")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "jane@example.com"  # normalized
    assert body["full_name"] == "Jane"  # trimmed
    assert "password" not in str(body)


async def test_register_duplicate_email_case_insensitive(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    response = await register(client, "JANE@example.com")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": DEFAULT_PASSWORD, "full_name": "X"},
        {"email": "a@example.com", "password": "short", "full_name": "X"},
        {"email": "a@example.com", "password": DEFAULT_PASSWORD, "full_name": "   "},
    ],
)
async def test_register_validation(client: AsyncClient, payload: dict) -> None:
    response = await client.post(f"{API}/register", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


# ---------- Login & /me ----------


async def test_login_and_me(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    tokens = await login(client, "jane@example.com")

    assert tokens["token_type"] == "bearer"
    response = await client.get(f"{API}/me", headers=bearer(tokens))
    assert response.status_code == 200
    assert response.json()["email"] == "jane@example.com"
    assert response.json()["organizations"] == []


async def test_login_errors_do_not_reveal_which_part_was_wrong(client: AsyncClient) -> None:
    await register(client, "jane@example.com")

    wrong_password = await client.post(
        f"{API}/login", json={"email": "jane@example.com", "password": "nope-nope"}
    )
    unknown_email = await client.post(
        f"{API}/login", json={"email": "ghost@example.com", "password": "nope-nope"}
    )

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json()["error"]["message"] == unknown_email.json()["error"]["message"]
    assert wrong_password.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "headers", [{}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"}]
)
async def test_me_requires_valid_token(client: AsyncClient, headers: dict) -> None:
    response = await client.get(f"{API}/me", headers=headers)

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    tokens = await login(client, "jane@example.com")

    response = await client.get(
        f"{API}/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"}
    )
    assert response.status_code == 401


# ---------- Refresh rotation ----------


async def test_refresh_rotates_tokens(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    first = await login(client, "jane@example.com")

    response = await client.post(f"{API}/refresh", json={"refresh_token": first["refresh_token"]})

    assert response.status_code == 200
    second = response.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert (await client.get(f"{API}/me", headers=bearer(second))).status_code == 200


async def test_reused_refresh_token_revokes_whole_session(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    first = await login(client, "jane@example.com")
    second = (
        await client.post(f"{API}/refresh", json={"refresh_token": first["refresh_token"]})
    ).json()

    # An attacker replays the old token...
    replay = await client.post(f"{API}/refresh", json={"refresh_token": first["refresh_token"]})
    assert replay.status_code == 401

    # ...so the legitimate newer token is revoked too (whole family killed).
    legit = await client.post(f"{API}/refresh", json={"refresh_token": second["refresh_token"]})
    assert legit.status_code == 401


async def test_other_sessions_survive_reuse_detection(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    laptop = await login(client, "jane@example.com")
    phone = await login(client, "jane@example.com")

    await client.post(f"{API}/refresh", json={"refresh_token": laptop["refresh_token"]})
    await client.post(f"{API}/refresh", json={"refresh_token": laptop["refresh_token"]})  # reuse

    response = await client.post(f"{API}/refresh", json={"refresh_token": phone["refresh_token"]})
    assert response.status_code == 200


async def test_unknown_refresh_token_rejected(client: AsyncClient) -> None:
    response = await client.post(f"{API}/refresh", json={"refresh_token": "made-up"})

    assert response.status_code == 401


# ---------- Logout, profile, password ----------


async def test_logout_revokes_refresh_token(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    tokens = await login(client, "jane@example.com")

    response = await client.post(f"{API}/logout", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 204

    response = await client.post(f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert response.status_code == 401


async def test_update_profile(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    tokens = await login(client, "jane@example.com")

    response = await client.patch(
        f"{API}/me", json={"full_name": "Jane Smith"}, headers=bearer(tokens)
    )

    assert response.status_code == 200
    assert response.json()["full_name"] == "Jane Smith"


async def test_change_password(client: AsyncClient) -> None:
    await register(client, "jane@example.com")
    tokens = await login(client, "jane@example.com")

    wrong = await client.post(
        f"{API}/change-password",
        json={"current_password": "not-it", "new_password": "brand-new-password"},
        headers=bearer(tokens),
    )
    assert wrong.status_code == 400

    ok = await client.post(
        f"{API}/change-password",
        json={"current_password": DEFAULT_PASSWORD, "new_password": "brand-new-password"},
        headers=bearer(tokens),
    )
    assert ok.status_code == 204

    # Old sessions are signed out; old password no longer works; new one does.
    old_refresh = await client.post(
        f"{API}/refresh", json={"refresh_token": tokens["refresh_token"]}
    )
    assert old_refresh.status_code == 401
    old_login = await client.post(
        f"{API}/login", json={"email": "jane@example.com", "password": DEFAULT_PASSWORD}
    )
    assert old_login.status_code == 401
    await login(client, "jane@example.com", "brand-new-password")
