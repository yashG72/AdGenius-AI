"""Start the API with a psycopg-compatible event loop (needed on Windows for TASK_MODE=inline).

With TASK_MODE=inline, campaign runs execute inside the API process, and their LangGraph
checkpointer uses psycopg, which cannot run on Windows' default ProactorEventLoop. The
plain `uvicorn` command uses that loop on Windows, so this launcher starts uvicorn on a
SelectorEventLoop instead. On Linux (e.g. Render) it behaves exactly like `uvicorn`.

    python -m scripts.serve            # HOST / PORT env vars, default 127.0.0.1:8000
"""

import os

import uvicorn

from app.core.aio import run_async


def main() -> None:
    config = uvicorn.Config(
        "app.main:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )
    run_async(uvicorn.Server(config).serve())


if __name__ == "__main__":
    main()
