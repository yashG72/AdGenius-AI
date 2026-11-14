"""Optional LangSmith tracing.

LangChain/LangGraph read tracing settings from environment variables. Our settings come
from .env via Pydantic (which does not export them), so we export them here when a
LangSmith key is configured. Every agent step and LLM call then appears in LangSmith as
one trace per workflow segment, tagged with the run's metadata (organization, campaign,
run id/version, attempt) so it can be filtered when debugging.
"""

import logging
import os

from app.core.config import Settings

logger = logging.getLogger(__name__)


def configure_tracing(settings: Settings) -> bool:
    if settings.langsmith_api_key is None or not settings.langsmith_api_key.get_secret_value():
        logger.info("LangSmith tracing disabled (LANGSMITH_API_KEY not set)")
        return False
    os.environ.setdefault("LANGSMITH_TRACING", "true")
    os.environ.setdefault("LANGSMITH_API_KEY", settings.langsmith_api_key.get_secret_value())
    os.environ.setdefault("LANGSMITH_PROJECT", settings.langsmith_project)
    logger.info("LangSmith tracing enabled (project %r)", settings.langsmith_project)
    return True
