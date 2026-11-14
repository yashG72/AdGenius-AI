"""Brands API: CRUD, validation, tenant isolation, soft delete and permissions."""

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.anyio

API = "/api/v1/brands"

FULL_PROFILE = {
    "name": "MANO",
    "description": "Premium sparkling beverage.",
    "industry": "Beverages",
    "website": "https://mano.example.com",
    "product_information": "Low-sugar sparkling drink in 4 flavours.",
    "target_audience": "College students aged 18-25",
    "brand_personality": "Playful, bold, witty",
    "brand_voice": "Casual and humorous, never sarcastic",
    "positioning": "The smart alternative to energy drinks",
    "messaging": "Refreshment without the crash",
    "brand_colors": [{"name": "Mango", "hex": "#FFB300"}, {"name": "Ink", "hex": "#1a1a1a"}],
    "marketing_objectives": ["Brand awareness", "Campus trial"],
    "content_restrictions": ["No health claims", "Never mention competitors by name"],
    "competitors": [{"name": "FizzCo", "website": "https://fizzco.example.com", "notes": "Leader"}],
    "social_links": [{"platform": "instagram", "url": "https://instagram.com/mano"}],
}


@pytest.fixture
async def workspace(client: AsyncClient, register_and_login):
    """Org A with an owner and a plain member; org B owned by an outsider."""
    owner = await register_and_login("owner@example.com")
    member = await register_and_login("member@example.com")
    outsider = await register_and_login("outsider@example.com")

    org_a = (await client.post("/api/v1/organizations", json={"name": "A"}, headers=owner)).json()
    org_b = (
        await client.post("/api/v1/organizations", json={"name": "B"}, headers=outsider)
    ).json()
    await client.post(
        f"/api/v1/organizations/{org_a['id']}/members",
        json={"email": "member@example.com"},
        headers=owner,
    )
    return {
        "org_a": org_a["id"],
        "org_b": org_b["id"],
        "owner": owner,
        "member": member,
        "outsider": outsider,
    }


async def create_brand(client: AsyncClient, headers: dict, org_id: str, **fields) -> dict:
    payload = {"organization_id": org_id, "name": "MANO", **fields}
    response = await client.post(API, json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


# ---------- Create & read ----------


async def test_create_brand_with_full_profile(client: AsyncClient, workspace) -> None:
    brand = await create_brand(client, workspace["member"], workspace["org_a"], **FULL_PROFILE)

    assert brand["organization_id"] == workspace["org_a"]
    assert brand["created_by_id"] is not None
    assert brand["brand_colors"][1] == {"name": "Ink", "hex": "#1a1a1a"}
    assert brand["content_restrictions"] == FULL_PROFILE["content_restrictions"]
    assert brand["competitors"][0]["name"] == "FizzCo"
    assert brand["website"].startswith("https://mano.example.com")

    fetched = await client.get(f"{API}/{brand['id']}", headers=workspace["member"])
    assert fetched.status_code == 200
    assert fetched.json() == brand


async def test_minimal_brand_gets_empty_lists(client: AsyncClient, workspace) -> None:
    brand = await create_brand(client, workspace["owner"], workspace["org_a"])

    assert brand["brand_colors"] == [] and brand["competitors"] == []
    assert brand["description"] is None


@pytest.mark.parametrize(
    "bad_fields",
    [
        {"brand_colors": [{"name": "Red", "hex": "red"}]},
        {"website": "not a url"},
        {"social_links": [{"platform": "x", "url": "javascript:alert(1)"}]},
        {"name": "   "},
        {"content_restrictions": [""]},
        {"marketing_objectives": ["x"] * 51},
    ],
)
async def test_create_validation(client: AsyncClient, workspace, bad_fields: dict) -> None:
    response = await client.post(
        API,
        json={"organization_id": workspace["org_a"], "name": "MANO", **bad_fields},
        headers=workspace["owner"],
    )
    assert response.status_code == 422


async def test_duplicate_name_is_case_insensitive_per_org(client: AsyncClient, workspace) -> None:
    await create_brand(client, workspace["owner"], workspace["org_a"], name="MANO")

    duplicate = await client.post(
        API,
        json={"organization_id": workspace["org_a"], "name": "mano"},
        headers=workspace["owner"],
    )
    assert duplicate.status_code == 409

    # The same name is fine in a different organization.
    await create_brand(client, workspace["outsider"], workspace["org_b"], name="MANO")


# ---------- Tenant isolation ----------


async def test_cannot_create_brand_in_foreign_org(client: AsyncClient, workspace) -> None:
    response = await client.post(
        API,
        json={"organization_id": workspace["org_b"], "name": "Sneaky"},
        headers=workspace["owner"],
    )
    assert response.status_code == 404


async def test_foreign_brand_is_invisible(client: AsyncClient, workspace) -> None:
    brand = await create_brand(client, workspace["owner"], workspace["org_a"])
    url, outsider = f"{API}/{brand['id']}", workspace["outsider"]

    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.patch(url, json={"name": "Hacked"}, headers=outsider)).status_code == 404
    assert (await client.delete(url, headers=outsider)).status_code == 404
    listed = await client.get(API, params={"organization_id": workspace["org_a"]}, headers=outsider)
    assert listed.status_code == 404


# ---------- List ----------


async def test_list_paginates_and_searches(client: AsyncClient, workspace) -> None:
    for name in ["Zeta", "Alpha", "Beta", "Alpha Max"]:
        await create_brand(client, workspace["owner"], workspace["org_a"], name=name)
    await create_brand(client, workspace["outsider"], workspace["org_b"], name="Other Org Brand")
    params = {"organization_id": workspace["org_a"]}

    page = (
        await client.get(API, params={**params, "limit": 2}, headers=workspace["member"])
    ).json()
    assert page["total"] == 4
    assert [b["name"] for b in page["items"]] == ["Alpha", "Alpha Max"]

    page2 = (
        await client.get(
            API, params={**params, "limit": 2, "offset": 2}, headers=workspace["member"]
        )
    ).json()
    assert [b["name"] for b in page2["items"]] == ["Beta", "Zeta"]

    found = (
        await client.get(API, params={**params, "search": "alpha"}, headers=workspace["member"])
    ).json()
    assert found["total"] == 2


async def test_search_wildcards_are_literal(client: AsyncClient, workspace) -> None:
    await create_brand(client, workspace["owner"], workspace["org_a"], name="Plain")

    response = await client.get(
        API,
        params={"organization_id": workspace["org_a"], "search": "%"},
        headers=workspace["owner"],
    )
    assert response.json()["total"] == 0


async def test_list_requires_organization_id(client: AsyncClient, workspace) -> None:
    response = await client.get(API, headers=workspace["owner"])

    assert response.status_code == 422


# ---------- Update ----------


async def test_partial_update_changes_only_sent_fields(client: AsyncClient, workspace) -> None:
    brand = await create_brand(client, workspace["owner"], workspace["org_a"], **FULL_PROFILE)

    response = await client.patch(
        f"{API}/{brand['id']}",
        json={"brand_voice": "Deadpan", "description": None, "competitors": []},
        headers=workspace["member"],
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["brand_voice"] == "Deadpan"
    assert updated["description"] is None  # explicitly cleared
    assert updated["competitors"] == []
    assert updated["positioning"] == FULL_PROFILE["positioning"]  # untouched
    assert updated["updated_at"] >= brand["updated_at"]


@pytest.mark.parametrize("field", ["name", "brand_colors", "content_restrictions"])
async def test_update_rejects_null_for_required_fields(
    client: AsyncClient, workspace, field: str
) -> None:
    brand = await create_brand(client, workspace["owner"], workspace["org_a"])

    response = await client.patch(
        f"{API}/{brand['id']}", json={field: None}, headers=workspace["owner"]
    )
    assert response.status_code == 422


async def test_rename_to_existing_name_conflicts(client: AsyncClient, workspace) -> None:
    await create_brand(client, workspace["owner"], workspace["org_a"], name="One")
    two = await create_brand(client, workspace["owner"], workspace["org_a"], name="Two")

    response = await client.patch(
        f"{API}/{two['id']}", json={"name": "ONE"}, headers=workspace["owner"]
    )
    assert response.status_code == 409

    # Renaming a brand to (a different case of) its own name is fine.
    same = await client.patch(
        f"{API}/{two['id']}", json={"name": "TWO"}, headers=workspace["owner"]
    )
    assert same.status_code == 200


# ---------- Delete ----------


async def test_member_cannot_delete_brand(client: AsyncClient, workspace) -> None:
    brand = await create_brand(client, workspace["owner"], workspace["org_a"])

    response = await client.delete(f"{API}/{brand['id']}", headers=workspace["member"])
    assert response.status_code == 403


async def test_soft_delete_hides_brand_and_frees_name(client: AsyncClient, workspace) -> None:
    brand = await create_brand(client, workspace["owner"], workspace["org_a"])

    response = await client.delete(f"{API}/{brand['id']}", headers=workspace["owner"])
    assert response.status_code == 204

    assert (await client.get(f"{API}/{brand['id']}", headers=workspace["owner"])).status_code == 404
    listed = await client.get(
        API, params={"organization_id": workspace["org_a"]}, headers=workspace["owner"]
    )
    assert listed.json()["total"] == 0
    # Name can be reused after deletion (partial unique index).
    await create_brand(client, workspace["owner"], workspace["org_a"], name="MANO")
