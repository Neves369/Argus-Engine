from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from app.core.config import get_settings
from app.llm import ChatMessage, LLMError, LLMRouter
from app.llm.providers import ProviderSpec, get_provider


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="ping")]


def _ok_response(model: str, prompt: int = 10, completion: int = 20) -> Response:
    return Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": "pong"}}],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
        },
    )


def test_route_for_mode():
    settings = get_settings()
    settings.execution_models = ["groq/exec-model", "openai/judge-model"]
    settings.judgment_models = ["openai/judge-model"]

    router = LLMRouter()
    assert router.route_for_mode(True) == [("groq", "exec-model"), ("openai", "judge-model")]
    assert router.route_for_mode(False) == [("openai", "judge-model")]


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    spec = ProviderSpec("groq", "https://api.groq.com/openai/v1", "GROQ_API_KEY", ())
    with pytest.raises(ValueError):
        _ = spec.api_key


@respx.mock
def test_complete_falls_back_to_next_provider():
    settings = get_settings()
    settings.judgment_models = ["groq/fail-model", "openai/ok-model"]

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(500, text="boom")
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_ok_response("ok-model")
    )

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    result = asyncio.run(_run())

    assert result.provider == "openai"
    assert result.model == "ok-model"
    assert result.content == "pong"
    assert result.strategy == "priority"
    assert result.decision["mode"] == "judgment"


@respx.mock
def test_complete_tracks_tokens_and_cost():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant"]

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant", prompt=1000, completion=500)
    )

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    result = asyncio.run(_run())

    provider = get_provider("groq")
    expected_cost = (1000 / 1_000_000) * provider.price_in + (500 / 1_000_000) * provider.price_out

    assert result.usage.prompt_tokens == 1000
    assert result.usage.completion_tokens == 500
    assert result.usage.total_tokens == 1500
    assert result.usage.cost == pytest.approx(expected_cost)


@respx.mock
def test_complete_all_fail_raises():
    settings = get_settings()
    settings.judgment_models = ["groq/fail-model", "openai/fail2"]

    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(503, text="down")
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(503, text="down")
    )

    async def _run() -> None:
        router = LLMRouter()
        try:
            with pytest.raises(LLMError):
                await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    asyncio.run(_run())


@respx.mock
def test_complete_no_combos_raises():
    settings = get_settings()
    settings.judgment_models = []

    async def _run() -> None:
        router = LLMRouter()
        try:
            with pytest.raises(LLMError):
                await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    asyncio.run(_run())
