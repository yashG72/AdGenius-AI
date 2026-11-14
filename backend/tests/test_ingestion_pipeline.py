"""End-to-end ingestion pipeline against a real (in-memory) Qdrant.

Uses a tiny deterministic fake embedder so tests are fast and need no model download.
"""

import hashlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import AsyncClient
from qdrant_client import AsyncQdrantClient, models
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import LocalFileStorage
from app.ingestion.embeddings import Embeddings, SparseVector
from app.ingestion.pipeline import ingest_document
from app.ingestion.vector_store import VectorStore
from app.models import BrandDocument, DocumentStatus
from tests.files import pdf_bytes

pytestmark = pytest.mark.anyio


class FakeEmbedder:
    dense_dim = 8

    def embed_documents(self, texts: list[str]) -> Embeddings:
        dense, sparse = [], []
        for text in texts:
            digest = hashlib.sha256(text.encode()).digest()
            dense.append([b / 255 + 0.01 for b in digest[: self.dense_dim]])
            words = sorted(
                {
                    int(hashlib.md5(w.encode()).hexdigest(), 16) % 10_000
                    for w in text.lower().split()
                }
            )
            sparse.append(SparseVector(indices=words, values=[1.0] * len(words)))
        return Embeddings(dense=dense, sparse=sparse)


class BrokenVectorStore(VectorStore):
    async def ensure_collection(self, dense_dim: int) -> None:
        raise ConnectionError("Qdrant is down")


@pytest.fixture
async def vector_store():
    client = AsyncQdrantClient(location=":memory:")
    yield VectorStore(client, "test_chunks")
    await client.close()


@pytest.fixture
def run(db_session: AsyncSession, storage: LocalFileStorage, vector_store: VectorStore):
    """Run the pipeline using the test DB session, temp storage and in-memory Qdrant."""

    @asynccontextmanager
    async def session_factory():
        yield db_session

    async def _run(document_id, *, store=None, force=False):
        return await ingest_document(
            uuid.UUID(str(document_id)),
            session_factory=session_factory,
            storage=storage,
            embedder=FakeEmbedder(),
            vector_store=store or vector_store,
            settings=get_settings(),
            force=force,
        )

    return _run


@pytest.fixture
async def brand_upload(client: AsyncClient, register_and_login):
    headers = await register_and_login("owner@example.com")
    org = (await client.post("/api/v1/organizations", json={"name": "A"}, headers=headers)).json()
    brand = (
        await client.post(
            "/api/v1/brands", json={"organization_id": org["id"], "name": "MANO"}, headers=headers
        )
    ).json()

    async def _upload(filename: str, data: bytes) -> dict:
        response = await client.post(
            f"/api/v1/brands/{brand['id']}/documents",
            files={"file": (filename, data, "application/octet-stream")},
            data={"document_type": "brand_guidelines"},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        return response.json()

    _upload.org_id, _upload.brand_id, _upload.headers = org["id"], brand["id"], headers
    return _upload


async def _points(store: VectorStore, document_id: str) -> list[models.Record]:
    if not await store.client.collection_exists(store.collection):
        return []
    records, _ = await store.client.scroll(
        store.collection,
        scroll_filter=models.Filter(
            must=[
                models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))
            ]
        ),
        limit=1000,
        with_payload=True,
    )
    return records


async def test_pdf_is_indexed_with_tenant_metadata(
    run, brand_upload, vector_store, db_session, tmp_path: Path
) -> None:
    doc = await brand_upload("guide.pdf", pdf_bytes(["Voice: witty.", "Colors: mango."], tmp_path))

    status = await run(doc["id"])

    assert status is DocumentStatus.INDEXED
    record = await db_session.get(BrandDocument, uuid.UUID(doc["id"]))
    assert record.chunk_count == 2 and record.page_count == 2
    assert record.indexed_at is not None and record.ingestion_attempts == 1

    points = await _points(vector_store, doc["id"])
    payloads = sorted((p.payload for p in points), key=lambda p: p["chunk_index"])
    assert [p["source_page"] for p in payloads] == [1, 2]
    for payload in payloads:
        assert payload["organization_id"] == brand_upload.org_id
        assert payload["brand_id"] == brand_upload.brand_id
        assert payload["document_id"] == doc["id"]
        assert payload["original_filename"] == "guide.pdf"
        assert payload["document_type"] == "brand_guidelines"
    assert "witty" in payloads[0]["text"]


async def test_rerun_is_idempotent(run, brand_upload, vector_store) -> None:
    doc = await brand_upload("notes.txt", b"Tone: playful. " * 400)

    await run(doc["id"])
    first = len(await _points(vector_store, doc["id"]))
    assert await run(doc["id"]) is DocumentStatus.INDEXED  # skipped: already indexed
    await run(doc["id"], force=True)  # forced re-index replaces, never duplicates

    assert first > 1
    assert len(await _points(vector_store, doc["id"])) == first


async def test_document_without_text_fails_permanently(
    run, brand_upload, db_session, tmp_path: Path
) -> None:
    doc = await brand_upload("scan.pdf", pdf_bytes([""], tmp_path))

    status = await run(doc["id"])

    assert status is DocumentStatus.FAILED
    record = await db_session.get(BrandDocument, uuid.UUID(doc["id"]))
    assert "No extractable text" in record.error_message


async def test_transient_error_marks_failed_and_reraises(
    run, brand_upload, vector_store, db_session
) -> None:
    doc = await brand_upload("notes.txt", b"Some text")
    broken = BrokenVectorStore(vector_store.client, vector_store.collection)

    with pytest.raises(ConnectionError):
        await run(doc["id"], store=broken)  # Celery would retry this

    record = await db_session.get(BrandDocument, uuid.UUID(doc["id"]))
    assert record.status is DocumentStatus.FAILED
    assert record.error_message == "Temporary error; retrying."


async def test_deleted_document_is_skipped(
    run, brand_upload, vector_store, client: AsyncClient
) -> None:
    doc = await brand_upload("notes.txt", b"Some text")
    await client.delete(f"/api/v1/documents/{doc['id']}", headers=brand_upload.headers)

    assert await run(doc["id"]) is DocumentStatus.DELETED
    assert await _points(vector_store, doc["id"]) == []


async def test_delete_document_vectors(run, brand_upload, vector_store) -> None:
    keep = await brand_upload("a.txt", b"Keep me")
    drop = await brand_upload("b.txt", b"Drop me")
    await run(keep["id"])
    await run(drop["id"])

    await vector_store.delete_document(uuid.UUID(drop["id"]))

    assert len(await _points(vector_store, keep["id"])) == 1
    assert await _points(vector_store, drop["id"]) == []
