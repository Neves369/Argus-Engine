from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from app.core.config import get_settings
from app.llm import ChatMessage, LLMRouter
from app.llm.providers import (
    clear_provider_api_key_overrides,
    clear_provider_enabled_overrides,
    get_provider,
)


@pytest.fixture(autouse=True)
def _reset_provider_state():
    clear_provider_api_key_overrides()
    clear_provider_enabled_overrides()
    yield
    clear_provider_api_key_overrides()
    clear_provider_enabled_overrides()


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="ping")]


def _ok_response(model: str, prompt: int = 1000, completion: int = 500) -> Response:
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


def test_gemini_provider_registered():
    spec = get_provider("gemini")
    assert spec.api_key_env == "GEMINI_API_KEY"
    # endpoint OpenAI-compat: o LLMClient anexa `/chat/completions`
    assert not spec.base_url.endswith("/")
    assert "gemini" in spec.models[0]


def test_gemini_listed_in_providers_api(client):
    body = client.get("/api/v1/providers").json()
    gemini = next(p for p in body["providers"] if p["provider"] == "gemini")
    assert gemini["key_source"] is None
    assert gemini["has_api_key"] is False


def test_gemini_key_source_env_when_set(monkeypatch, client):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    body = client.get("/api/v1/providers").json()
    gemini = next(p for p in body["providers"] if p["provider"] == "gemini")
    assert gemini["key_source"] == "env"
    assert gemini["has_api_key"] is True


@respx.mock
def test_gemini_complete_uses_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini")
    monkeypatch.setattr(
        get_settings(), "judgment_models", ["gemini/gemini-2.5-flash"]
    )

    route = respx.post(
        "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    ).mock(return_value=_ok_response("gemini-2.5-flash"))

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    result = asyncio.run(_run())

    assert result.provider == "gemini"
    assert result.model == "gemini-2.5-flash"
    assert route.call_count == 1


@respx.mock
def test_gemini_without_key_falls_back_to_next_provider(monkeypatch):
    monkeypatch.setattr(
        get_settings(),
        "judgment_models",
        ["gemini/gemini-2.5-flash", "openai/gpt-4o-mini"],
    )

    fallback_route = respx.post(
        "https://api.openai.com/v1/chat/completions"
    ).mock(return_value=_ok_response("gpt-4o-mini"))

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    result = asyncio.run(_run())

    assert result.provider == "openai"
    assert fallback_route.call_count == 1