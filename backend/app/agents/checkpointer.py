"""Durable LangGraph checkpoints in PostgreSQL.

After every step, LangGraph saves the workflow state ("checkpoint") under the run's
thread_id. That is what lets a campaign run pause for human approval, survive a worker
restart, and resume exactly where it stopped.

The checkpoint tables live in their own `langgraph` schema: LangGraph creates and
migrates them itself (`setup()`), so they are kept apart from our Alembic-managed
`public` schema.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from urllib.parse import quote

import psycopg
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

CHECKPOINT_SCHEMA = "langgraph"


def psycopg_conninfo(database_url: str) -> str:
    """SQLAlchemy URL (postgresql+asyncpg://...) -> libpq URL for psycopg."""
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


@asynccontextmanager
async def postgres_checkpointer(database_url: str) -> AsyncIterator[AsyncPostgresSaver]:
    conninfo = psycopg_conninfo(database_url)
    async with await psycopg.AsyncConnection.connect(conninfo, autocommit=True) as conn:
        await conn.execute(f"CREATE SCHEMA IF NOT EXISTS {CHECKPOINT_SCHEMA}")

    separator = "&" if "?" in conninfo else "?"
    scoped = f"{conninfo}{separator}options={quote(f'-c search_path={CHECKPOINT_SCHEMA}')}"
    async with AsyncPostgresSaver.from_conn_string(scoped) as saver:
        await saver.setup()  # idempotent: creates/migrates checkpoint tables
        yield saver
