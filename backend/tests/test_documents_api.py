"""Documents API: upload validation, tenant isolation, duplicates, delete, reindex."""

from pathlib import Path

import pytest
from httpx import AsyncClient

from app.core.config import get_settings
from app.core.storage import LocalFileStorage
from tests.files import docx_bytes, pdf_bytes

pytestmark = pytest.mark.anyio

TXT = ("guidelines.txt", b"MANO brand guidelines: be witty, never mean.", "text/plain")


@pytest.fixture
async def ws(client: AsyncClient, register_and_login):
    owner = await register_and_login("owner@example.com")
    member = await register_and_login("member@example.com")
    outsider = await register_and_login("outsider@example.com")
    org = (await client.post("/api/v1/organizations", json={"name": "A"}, headers=owner)).json()
    await client.post(
        f"/api/v1/organizations/{org['id']}/members",
        json={"email": "member@example.com"},
        headers=owner,
    )
    brand = (
        await client.post(
            "/api/v1/brands", json={"organization_id": org["id"], "name": "MANO"}, headers=owner
        )
    ).json()
    return {
        "org": org["id"],
        "brand": brand["id"],
        "owner": owner,
        "member": member,
        "outsider": outsider,
    }


async def upload(client: AsyncClient, ws, file=TXT, headers=None, doc_type="brand_guidelines"):
    return await client.post(
        f"/api/v1/brands/{ws['brand']}/documents",
        files={"file": file},
        data={"document_type": doc_type},
        headers=headers or ws["member"],
    )


# ---------- Upload ----------


async def test_upload_stores_file_and_queues_ingestion(
    client: AsyncClient, ws, queued, storage: LocalFileStorage
) -> None:
    response = await upload(client, ws)

    assert response.status_code == 201, response.text
    doc = response.json()
    assert doc["status"] == "pending"
    assert doc["file_format"] == "txt"
    assert doc["document_type"] == "brand_guidelines"
    assert doc["organization_id"] == ws["org"]
    assert doc["size_bytes"] == len(TXT[1])
    assert [str(d) for d, _ in queued["ingest"]] == [doc["id"]]

    stored = list((storage.root / ws["org"] / ws["brand"]).iterdir())
    assert [p.name for p in stored] == [f"{doc['id']}.txt"]  # named by id, not by user input
    assert stored[0].read_bytes() == TXT[1]


@pytest.mark.parametrize("kind", ["pdf", "docx"])
async def test_upload_real_pdf_and_docx(client: AsyncClient, ws, tmp_path: Path, kind) -> None:
    data = pdf_bytes(["Hello"], tmp_path) if kind == "pdf" else docx_bytes(["Hello"], tmp_path)

    response = await upload(client, ws, file=(f"file.{kind}", data, "application/octet-stream"))

    assert response.status_code == 201, response.text
    assert response.json()["file_format"] == kind


@pytest.mark.parametrize(
    ("file", "status", "code"),
    [
        (("virus.exe", b"MZ...", "application/octet-stream"), 415, "unsupported_media_type"),
        (("fake.pdf", b"MZ not a pdf", "application/pdf"), 415, "unsupported_media_type"),
        (("bin.txt", b"\x00\x01\x02", "text/plain"), 415, "unsupported_media_type"),
        (("empty.txt", b"", "text/plain"), 400, "bad_request"),
    ],
)
async def test_upload_rejects_bad_files(
    client: AsyncClient, ws, queued, file, status, code
) -> None:
    response = await upload(client, ws, file=file)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert queued["ingest"] == []


async def test_upload_size_limit(client: AsyncClient, ws) -> None:
    app = client._transport.app
    small = get_settings().model_copy(update={"max_upload_size_mb": 1})
    app.dependency_overrides[get_settings] = lambda: small

    response = await upload(client, ws, file=("big.txt", b"a" * (1024 * 1024 + 1), "text/plain"))

    assert response.status_code == 413


async def test_invalid_document_type(client: AsyncClient, ws) -> None:
    response = await upload(client, ws, doc_type="secret_plans")

    assert response.status_code == 422


async def test_duplicate_upload_conflicts(client: AsyncClient, ws) -> None:
    first = (await upload(client, ws)).json()

    duplicate = await upload(client, ws, file=("renamed.txt", TXT[1], "text/plain"))

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["details"]["document_id"] == first["id"]


# ---------- Isolation ----------


async def test_outsider_cannot_upload_or_read(client: AsyncClient, ws) -> None:
    doc = (await upload(client, ws)).json()

    assert (await upload(client, ws, headers=ws["outsider"])).status_code == 404
    assert (
        await client.get(f"/api/v1/documents/{doc['id']}", headers=ws["outsider"])
    ).status_code == 404
    assert (
        await client.get(f"/api/v1/brands/{ws['brand']}/documents", headers=ws["outsider"])
    ).status_code == 404


# ---------- List / get ----------


async def test_list_and_filter_by_status(client: AsyncClient, ws) -> None:
    await upload(client, ws)
    await upload(client, ws, file=("other.txt", b"Different content", "text/plain"))
    url = f"/api/v1/brands/{ws['brand']}/documents"

    all_docs = (await client.get(url, headers=ws["member"])).json()
    pending = (await client.get(url, params={"status": "pending"}, headers=ws["member"])).json()
    indexed = (await client.get(url, params={"status": "indexed"}, headers=ws["member"])).json()

    assert all_docs["total"] == 2 and pending["total"] == 2 and indexed["total"] == 0


# ---------- Delete / reindex ----------


async def test_delete_requires_admin_and_queues_cleanup(client: AsyncClient, ws, queued) -> None:
    doc = (await upload(client, ws)).json()
    url = f"/api/v1/documents/{doc['id']}"

    assert (await client.delete(url, headers=ws["member"])).status_code == 403
    assert (await client.delete(url, headers=ws["owner"])).status_code == 204

    assert [str(d) for d in queued["cleanup"][0][0]] == [doc["id"]]
    assert (await client.get(url, headers=ws["owner"])).status_code == 404
    # The same file can be uploaded again after deletion.
    assert (await upload(client, ws)).status_code == 201


async def test_reindex_queues_forced_ingestion(client: AsyncClient, ws, queued) -> None:
    doc = (await upload(client, ws)).json()

    response = await client.post(f"/api/v1/documents/{doc['id']}/reindex", headers=ws["member"])

    assert response.status_code == 202
    assert response.json()["status"] == "pending"
    assert queued["ingest"][-1][1] is True  # force=True


async def test_deleting_brand_deletes_its_documents(client: AsyncClient, ws, queued) -> None:
    doc = (await upload(client, ws)).json()

    response = await client.delete(f"/api/v1/brands/{ws['brand']}", headers=ws["owner"])

    assert response.status_code == 204
    assert str(queued["cleanup"][-1][1]) == ws["brand"]
    assert (
        await client.get(f"/api/v1/documents/{doc['id']}", headers=ws["owner"])
    ).status_code == 404
