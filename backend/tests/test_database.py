"""Phase 1 database layer: migrations, models, constraints, readiness check."""

import uuid

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models import Base, Membership, MembershipRole, Organization, User

pytestmark = pytest.mark.anyio


async def make_user(session: AsyncSession, email: str = "jane@example.com") -> User:
    user = User(email=email, password_hash="not-a-real-hash", full_name="Jane Doe")
    session.add(user)
    await session.flush()  # send INSERT now so DB defaults/constraints apply
    return user


async def make_org(session: AsyncSession, slug: str = "acme") -> Organization:
    org = Organization(name="Acme Creative", slug=slug)
    session.add(org)
    await session.flush()
    return org


# ---------- Migrations ----------


async def test_migrations_match_models(db_session: AsyncSession) -> None:
    """Fails if someone changes a model but forgets to create a migration."""
    connection = await db_session.connection()

    def diff(sync_connection):
        return compare_metadata(MigrationContext.configure(sync_connection), Base.metadata)

    assert await connection.run_sync(diff) == []


# ---------- Models & defaults ----------


async def test_create_org_user_membership(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    membership = Membership(organization_id=org.id, user_id=user.id)
    db_session.add(membership)
    await db_session.flush()
    await db_session.refresh(user)  # reload server-generated columns

    assert isinstance(org.id, uuid.UUID)
    assert user.is_active is True
    assert user.created_at is not None and user.created_at.tzinfo is not None
    assert membership.role is MembershipRole.MEMBER


# ---------- Constraints ----------


async def test_email_must_be_unique(db_session: AsyncSession) -> None:
    await make_user(db_session, "dup@example.com")

    with pytest.raises(IntegrityError, match="uq_users_email"):
        await make_user(db_session, "dup@example.com")


async def test_email_must_be_lowercase(db_session: AsyncSession) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        await make_user(db_session, "Jane@Example.com")


async def test_user_cannot_join_same_org_twice(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    db_session.add(Membership(organization_id=org.id, user_id=user.id))
    await db_session.flush()

    db_session.add(Membership(organization_id=org.id, user_id=user.id))
    with pytest.raises(IntegrityError, match="uq_memberships_organization_id_user_id"):
        await db_session.flush()


async def test_deleting_org_cascades_to_memberships(db_session: AsyncSession) -> None:
    org = await make_org(db_session)
    user = await make_user(db_session)
    db_session.add(Membership(organization_id=org.id, user_id=user.id))
    await db_session.flush()

    await db_session.execute(delete(Organization).where(Organization.id == org.id))

    remaining = await db_session.scalar(select(func.count()).select_from(Membership))
    assert remaining == 0
    # The user account itself survives - only the membership goes.
    assert await db_session.get(User, user.id) is not None


# ---------- Readiness endpoint ----------


async def test_readiness_ok(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok"}}


async def test_readiness_returns_503_when_database_down(client: AsyncClient) -> None:
    class BrokenSession:
        async def execute(self, *args, **kwargs):
            raise ConnectionRefusedError("db down")

    async def broken_session():
        yield BrokenSession()

    client._transport.app.dependency_overrides[get_db_session] = broken_session

    response = await client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
