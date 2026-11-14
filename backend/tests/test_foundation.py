"""Phase 0 foundation: health, request IDs, error envelope."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio


async def test_health_returns_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "AdGenius AI"


async def test_request_id_is_generated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    assert len(response.headers["X-Request-ID"]) == 32


async def test_valid_client_request_id_is_echoed(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "abc-123"})

    assert response.headers["X-Request-ID"] == "abc-123"


async def test_unsafe_client_request_id_is_replaced(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={"X-Request-ID": "bad id;drop"})

    assert response.headers["X-Request-ID"] != "bad id;drop"


async def test_unknown_route_uses_error_envelope(client: AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist", headers={"X-Request-ID": "req-1"})

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == "req-1"
