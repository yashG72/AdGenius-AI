"""Organizations API: creation, tenant isolation, RBAC and membership rules."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

API = "/api/v1/organizations"


async def create_org(client: AsyncClient, headers: dict, name: str = "Acme Creative", **extra):
    response = await client.post(API, json={"name": name, **extra}, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def user_id(client: AsyncClient, headers: dict) -> str:
    return (await client.get("/api/v1/auth/me", headers=headers)).json()["id"]


@pytest.fixture
async def team(client: AsyncClient, register_and_login):
    """An org with an owner, an admin and a member, plus an outsider."""
    owner = await register_and_login("owner@example.com")
    admin = await register_and_login("admin@example.com")
    member = await register_and_login("member@example.com")
    outsider = await register_and_login("outsider@example.com")
    org = await create_org(client, owner)
    for email, role in [("admin@example.com", "admin"), ("member@example.com", "member")]:
        response = await client.post(
            f"{API}/{org['id']}/members", json={"email": email, "role": role}, headers=owner
        )
        assert response.status_code == 201, response.text
    return {"org": org, "owner": owner, "admin": admin, "member": member, "outsider": outsider}


# ---------- Creation ----------


async def test_creator_becomes_owner(client: AsyncClient, register_and_login) -> None:
    headers = await register_and_login("jane@example.com")

    org = await create_org(client, headers, "Acme Creative!")

    assert org["role"] == "owner"
    assert org["slug"] == "acme-creative"
    me = (await client.get("/api/v1/auth/me", headers=headers)).json()
    assert [o["id"] for o in me["organizations"]] == [org["id"]]


async def test_auto_slug_avoids_collisions(client: AsyncClient, register_and_login) -> None:
    headers = await register_and_login("jane@example.com")

    first = await create_org(client, headers, "Acme")
    second = await create_org(client, headers, "Acme")

    assert first["slug"] == "acme"
    assert second["slug"].startswith("acme-") and second["slug"] != "acme"


async def test_explicit_duplicate_slug_conflicts(client: AsyncClient, register_and_login) -> None:
    headers = await register_and_login("jane@example.com")
    await create_org(client, headers, slug="taken-slug")

    response = await client.post(
        API, json={"name": "Other", "slug": "taken-slug"}, headers=headers
    )
    assert response.status_code == 409


async def test_invalid_slug_rejected(client: AsyncClient, register_and_login) -> None:
    headers = await register_and_login("jane@example.com")

    response = await client.post(API, json={"name": "X", "slug": "Bad Slug!"}, headers=headers)
    assert response.status_code == 422


async def test_requires_authentication(client: AsyncClient) -> None:
    assert (await client.get(API)).status_code == 401


# ---------- Tenant isolation ----------


async def test_outsider_cannot_see_org(client: AsyncClient, team) -> None:
    org_id, outsider = team["org"]["id"], team["outsider"]

    assert (await client.get(f"{API}/{org_id}", headers=outsider)).status_code == 404
    assert (await client.get(f"{API}/{org_id}/members", headers=outsider)).status_code == 404
    patch = await client.patch(f"{API}/{org_id}", json={"name": "Hacked"}, headers=outsider)
    assert patch.status_code == 404
    listed = (await client.get(API, headers=outsider)).json()["items"]
    assert listed == []


async def test_members_see_org_with_their_role(client: AsyncClient, team) -> None:
    response = await client.get(f"{API}/{team['org']['id']}", headers=team["member"])

    assert response.status_code == 200
    assert response.json()["role"] == "member"
    members = (
        await client.get(f"{API}/{team['org']['id']}/members", headers=team["member"])
    ).json()["items"]
    assert sorted(m["role"] for m in members) == ["admin", "member", "owner"]


# ---------- RBAC ----------


async def test_only_admins_can_update_org(client: AsyncClient, team) -> None:
    url = f"{API}/{team['org']['id']}"

    denied = await client.patch(url, json={"name": "New"}, headers=team["member"])
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "permission_denied"

    allowed = await client.patch(url, json={"name": "New Name"}, headers=team["admin"])
    assert allowed.status_code == 200
    assert allowed.json()["name"] == "New Name"


async def test_member_cannot_add_members(client: AsyncClient, team, register_and_login) -> None:
    await register_and_login("new@example.com")

    response = await client.post(
        f"{API}/{team['org']['id']}/members",
        json={"email": "new@example.com"},
        headers=team["member"],
    )
    assert response.status_code == 403


async def test_add_member_errors(client: AsyncClient, team) -> None:
    url = f"{API}/{team['org']['id']}/members"

    unknown = await client.post(url, json={"email": "ghost@example.com"}, headers=team["owner"])
    assert unknown.status_code == 404
    duplicate = await client.post(
        url, json={"email": "member@example.com"}, headers=team["owner"]
    )
    assert duplicate.status_code == 409


async def test_admin_cannot_grant_or_touch_owner(client: AsyncClient, team) -> None:
    org_id = team["org"]["id"]
    member_id = await user_id(client, team["member"])
    owner_id = await user_id(client, team["owner"])

    grant = await client.patch(
        f"{API}/{org_id}/members/{member_id}", json={"role": "owner"}, headers=team["admin"]
    )
    assert grant.status_code == 403
    remove_owner = await client.delete(f"{API}/{org_id}/members/{owner_id}", headers=team["admin"])
    assert remove_owner.status_code == 403


async def test_admin_can_promote_member_to_admin(client: AsyncClient, team) -> None:
    member_id = await user_id(client, team["member"])

    response = await client.patch(
        f"{API}/{team['org']['id']}/members/{member_id}",
        json={"role": "admin"},
        headers=team["admin"],
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"


async def test_last_owner_cannot_leave_or_be_demoted(client: AsyncClient, team) -> None:
    org_id = team["org"]["id"]
    owner_id = await user_id(client, team["owner"])

    leave = await client.delete(f"{API}/{org_id}/members/{owner_id}", headers=team["owner"])
    assert leave.status_code == 409
    demote = await client.patch(
        f"{API}/{org_id}/members/{owner_id}", json={"role": "admin"}, headers=team["owner"]
    )
    assert demote.status_code == 409


async def test_owner_can_hand_over_ownership(client: AsyncClient, team) -> None:
    org_id = team["org"]["id"]
    admin_id = await user_id(client, team["admin"])
    owner_id = await user_id(client, team["owner"])

    promote = await client.patch(
        f"{API}/{org_id}/members/{admin_id}", json={"role": "owner"}, headers=team["owner"]
    )
    assert promote.status_code == 200
    leave = await client.delete(f"{API}/{org_id}/members/{owner_id}", headers=team["owner"])
    assert leave.status_code == 204


async def test_member_can_leave_but_not_remove_others(client: AsyncClient, team) -> None:
    org_id = team["org"]["id"]
    admin_id = await user_id(client, team["admin"])
    member_id = await user_id(client, team["member"])

    kick = await client.delete(f"{API}/{org_id}/members/{admin_id}", headers=team["member"])
    assert kick.status_code == 403

    leave = await client.delete(f"{API}/{org_id}/members/{member_id}", headers=team["member"])
    assert leave.status_code == 204
    assert (await client.get(f"{API}/{org_id}", headers=team["member"])).status_code == 404
