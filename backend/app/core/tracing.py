"""Optional LangSmith tracing.

LangChain/LangGraph read tracing settings from environment variables. Our settings come
from .env via Pydantic (which does not export them), so we export them here when a
LangSmith key is configured. Every agent step and LLM call then appears in LangSmith,
grouped per campaign run (thread_id is attached as metadata).
"""

import os

from app.core.config import Settings


def configure_tracing(settings: Settings) -> bool:
    if settings.langsmith_api_key is None or not settings.langsmith_api_key.get_secret_value():
        return False
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key.get_secret_value())
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    return True
