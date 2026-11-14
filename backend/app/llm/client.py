"""Structured LLM calls via LangChain + Google Gemini.

All LLM output in this project is *structured*: the caller passes a Pydantic schema and
gets back a validated instance, never free text it has to parse. That is what makes
agent outputs reliable enough to store, route on and display.

`StructuredLLM` is a tiny interface so the rest of the code (and the tests, which use a
fake) never depend on a specific provider.
"""

import logging
from functools import lru_cache
from typing import Protocol, TypeVar

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.core.config import Settings, get_settings
from app.core.exceptions import ServiceUnavailableError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMNotConfiguredError(ServiceUnavailableError):
    code = "llm_not_configured"
    message = "No LLM is configured. Set GOOGLE_API_KEY in backend/.env."


class LLMError(ServiceUnavailableError):
    code = "llm_error"
    message = "The language model request failed. Please try again."


class StructuredLLM(Protocol):
    async def generate(self, schema: type[T], *, system: str, user: str) -> T: ...


class GeminiLLM:
    """Primary model with an optional fallback model.

    Free-tier endpoints have overload periods (e.g. 504 DEADLINE_EXCEEDED). If the
    primary model fails, the same request goes to the fallback model before giving up.
    """

    def __init__(self, settings: Settings) -> None:
        from langchain_google_genai import ChatGoogleGenerativeAI

        assert settings.google_api_key is not None
        self.model_name = settings.llm_model
        names = [settings.llm_model]
        if settings.llm_fallback_model and settings.llm_fallback_model != settings.llm_model:
            names.append(settings.llm_fallback_model)
        self._models = [
            (
                name,
                ChatGoogleGenerativeAI(
                    model=name,
                    google_api_key=settings.google_api_key.get_secret_value(),
                    temperature=settings.llm_temperature,
                    timeout=settings.llm_timeout_seconds,
                    max_retries=settings.llm_max_retries,
                ),
            )
            for name in names
        ]

    async def generate(self, schema: type[T], *, system: str, user: str) -> T:
        messages = [SystemMessage(system), HumanMessage(user)]
        last_error: Exception | None = None
        for name, model in self._models:
            try:
                result = await model.with_structured_output(schema).ainvoke(messages)
            except Exception as exc:
                logger.warning("LLM call to %s failed (%s): %s", name, type(exc).__name__, exc)
                last_error = exc
                continue
            if isinstance(result, schema):
                return result
            last_error = LLMError(f"{name} returned an invalid response.")
        raise LLMError() from last_error


@lru_cache
def get_llm() -> StructuredLLM | None:
    """The configured LLM, or None when no API key is set (features degrade gracefully)."""
    settings = get_settings()
    if settings.google_api_key is None or not settings.google_api_key.get_secret_value():
        logger.info("GOOGLE_API_KEY not set: LLM features (rewriting, answers) disabled")
        return None
    return GeminiLLM(settings)
