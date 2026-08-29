from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from app.core.config import get_settings
from app.llm import ChatMessage, LLMError, LLMRouter
from app.llm.providers import ProviderSpec, get_provider


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")


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


def test_route_for_mode_cost_optimized_orders_by_price():
    settings = get_settings()
    # groq: 0.59+0.79=1.38 · openai: 0.15+0.60=0.75 · openrouter: 0.0
    settings.judgment_models = [
        "groq/llama-3.1-8b-instant",
        "openai/gpt-4o-mini",
        "openrouter/openrouter/auto",
    ]

    router = LLMRouter()
    ordered = router.route_for_mode(False, strategy="cost-optimized")

    assert ordered == [
        ("openrouter", "openrouter/auto"),
        ("openai", "gpt-4o-mini"),
        ("groq", "llama-3.1-8b-instant"),
    ]


def test_route_for_mode_auto_is_cost_optimized_for_judgment_only():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant", "openai/gpt-4o-mini"]
    settings.execution_models = ["groq/llama-3.1-8b-instant", "openai/gpt-4o-mini"]

    router = LLMRouter()

    # judgment (devil_mode=False): auto reorders by cost, cheapest (openai) first
    assert router.route_for_mode(False, strategy="auto") == [
        ("openai", "gpt-4o-mini"),
        ("groq", "llama-3.1-8b-instant"),
    ]
    # execution (devil_mode=True): auto keeps the declared priority order
    assert router.route_for_mode(True, strategy="auto") == [
        ("groq", "llama-3.1-8b-instant"),
        ("openai", "gpt-4o-mini"),
    ]


def test_route_for_mode_unknown_strategy_raises():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant"]

    router = LLMRouter()
    with pytest.raises(ValueError):
        router.route_for_mode(False, strategy="not-a-strategy")


@respx.mock
def test_complete_cost_optimized_tries_cheapest_first():
    settings = get_settings()
    settings.judgment_models = ["groq/expensive-model", "openai/cheap-model"]

    groq_route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("expensive-model")
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_ok_response("cheap-model")
    )

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(
                _messages(), devil_mode=False, strategy="cost-optimized"
            )
        finally:
            await router.close()

    result = asyncio.run(_run())

    assert result.provider == "openai"
    assert result.model == "cheap-model"
    assert result.strategy == "cost-optimized"
    assert not groq_route.called


@respx.mock
def test_attempt_completion_uses_configured_default_strategy():
    from app.llm.router import attempt_completion

    settings = get_settings()
    settings.judgment_models = ["groq/expensive-model", "openai/cheap-model"]
    settings.llm_strategy = "cost-optimized"

    groq_route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("expensive-model")
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_ok_response("cheap-model")
    )

    result = asyncio.run(attempt_completion("system", "user"))

    assert result is not None
    assert result.provider == "openai"
    assert result.strategy == "cost-optimized"
    assert not groq_route.called

    settings.llm_strategy = "priority"  # reset shared singleton for other tests


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
