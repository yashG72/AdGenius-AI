"""Shared pytest fixtures.

Database strategy:
1. Once per test session, the TEST database is reset and migrated with Alembic
   (so every run also proves the migrations work from scratch).
2. Each test runs inside a transaction that is rolled back afterwards, so tests are
   isolated from each other and leave no data behind.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings
from app.db.session import get_db_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests on asyncio (anyio's pytest plugin ships with FastAPI)."""
    return "asyncio"


@pytest.fixture(scope="session")
def test_database_url() -> str:
    settings = get_settings()
    url = settings.test_database_url
    if not url:
        pytest.exit("TEST_DATABASE_URL is not set in backend/.env", returncode=1)
    if url == settings.database_url:
        pytest.exit("TEST_DATABASE_URL must differ from DATABASE_URL (it gets wiped)", returncode=1)
    return url


@pytest.fixture(scope="session")
def migrated_database(test_database_url: str) -> str:
    """Wipe the test DB and apply all migrations from scratch."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", test_database_url.replace("%", "%%"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    return test_database_url


@pytest.fixture
async def db_session(migrated_database: str) -> AsyncIterator[AsyncSession]:
    """A session bound to an outer transaction that is always rolled back.

    join_transaction_mode="create_savepoint" means code under test can call
    session.commit()/rollback() freely: those act on a SAVEPOINT, never the outer
    transaction.
    """
    engine = create_async_engine(migrated_database, poolclass=NullPool)
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()
    await engine.dispose()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """HTTP client calling the app in-process, with the DB swapped for the test session."""
    app = create_app()

    async def override_get_db_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_db_session] = override_get_db_session

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client


DEFAULT_PASSWORD = "correct-horse-battery"


@pytest.fixture
def register_and_login(client: AsyncClient):
    """Factory: create a user via the API and return auth headers for them.

    Usage: headers = await register_and_login("alice@example.com")
    """

    async def _register_and_login(email: str, password: str = DEFAULT_PASSWORD) -> dict:
        response = await client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": password, "full_name": email.split("@")[0]},
        )
        assert response.status_code == 201, response.text
        response = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": password}
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _register_and_login
