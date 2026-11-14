"""GeminiLLM primary -> fallback model behaviour (no network: models are stubbed)."""

import pytest
from pydantic import BaseModel, SecretStr

from app.core.config import get_settings
from app.llm.client import GeminiLLM, LLMError

pytestmark = pytest.mark.anyio


class Out(BaseModel):
    value: str


class StubModel:
    def __init__(self, outcome):
        self.outcome, self.calls = outcome, 0

    def with_structured_output(self, schema):
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def llm_with(primary, fallback) -> GeminiLLM:
    settings = get_settings().model_copy(update={"google_api_key": SecretStr("test-key")})
    llm = GeminiLLM(settings)
    llm._models = [("primary", primary), ("fallback", fallback)]
    return llm


async def test_primary_success_skips_fallback() -> None:
    primary, fallback = StubModel(Out(value="a")), StubModel(Out(value="b"))

    assert (await llm_with(primary, fallback).generate(Out, system="s", user="u")).value == "a"
    assert fallback.calls == 0


async def test_falls_back_when_primary_fails() -> None:
    primary, fallback = StubModel(TimeoutError("504")), StubModel(Out(value="b"))

    assert (await llm_with(primary, fallback).generate(Out, system="s", user="u")).value == "b"
    assert primary.calls == 1


async def test_invalid_output_also_triggers_fallback() -> None:
    primary, fallback = StubModel(None), StubModel(Out(value="b"))

    assert (await llm_with(primary, fallback).generate(Out, system="s", user="u")).value == "b"


async def test_raises_when_all_models_fail() -> None:
    with pytest.raises(LLMError):
        await llm_with(StubModel(TimeoutError()), StubModel(TimeoutError())).generate(
            Out, system="s", user="u"
        )
