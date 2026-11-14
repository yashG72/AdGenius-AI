"""Async engine and session factory.

One engine (connection pool) per process. Each HTTP request gets its own short-lived
AsyncSession via the `get_db_session` dependency.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

_settings = get_settings()

# Creating the engine does not connect yet; connections open lazily on first use.
engine = create_async_engine(
    _settings.database_url,
    echo=_settings.database_echo,
    pool_size=_settings.database_pool_size,
    max_overflow=_settings.database_max_overflow,
    pool_pre_ping=True,  # transparently replace connections the server has dropped
)

SessionFactory = async_sessionmaker(
    engine,
    expire_on_commit=False,  # objects stay readable after commit (needed for async)
    autoflush=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session per request.

    Writes must be committed explicitly by the service layer (`await session.commit()`).
    Anything uncommitted is rolled back when the request ends.
    """
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
