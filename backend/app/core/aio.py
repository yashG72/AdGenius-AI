"""Event-loop helpers.

psycopg (used by the LangGraph Postgres checkpointer) cannot run its async mode on
Windows' default ProactorEventLoop, so code that drives agent workflows outside the
web server (Celery tasks, CLI scripts) runs on a SelectorEventLoop there.
"""

import asyncio
import sys
from collections.abc import Callable, Coroutine
from typing import Any, TypeVar

T = TypeVar("T")


def loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    return asyncio.SelectorEventLoop if sys.platform == "win32" else None


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Like asyncio.run(), but psycopg-compatible on Windows."""
    with asyncio.Runner(loop_factory=loop_factory()) as runner:
        return runner.run(coro)
