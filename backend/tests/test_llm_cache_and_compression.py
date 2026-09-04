from __future__ import annotations

import asyncio
import time

import pytest
import respx
from httpx import Response

from app.core.config import get_settings
from app.llm import ChatMessage, LLMRouter
from app.llm.cache import PrefixCache
from app.llm.compress import cap_length, compress_messages, normalize_whitespace


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")


def _messages(content: str = "ping") -> list[ChatMessage]:
    return [ChatMessage(role="user", content=content)]


def _ok_response(model: str, content: str = "pong") -> Response:
    return Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
        },
    )


# --- PrefixCache (unit) -----------------------------------------------------


def test_prefix_cache_hit_and_miss():
    cache = PrefixCache(ttl_seconds=60)
    assert cache.get("groq", "m", _messages(), 0.0, None) is None

    from app.llm.types import CompletionResult, TokenUsage

    result = CompletionResult(
        provider="groq",
        model="m",
        content="hi",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost=0.0),
    )
    cache.set("groq", "m", _messages(), 0.0, None, result)

    hit = cache.get("groq", "m", _messages(), 0.0, None)
    assert hit is not None
    assert hit.content == "hi"
    # different content -> different key -> miss
    assert cache.get("groq", "m", _messages("other"), 0.0, None) is None


def test_prefix_cache_returns_independent_copy():
    from app.llm.types import CompletionResult, TokenUsage

    cache = PrefixCache(ttl_seconds=60)
    result = CompletionResult(
        provider="groq",
        model="m",
        content="hi",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost=0.0),
        decision={"a": 1},
    )
    cache.set("groq", "m", _messages(), 0.0, None, result)

    first = cache.get("groq", "m", _messages(), 0.0, None)
    first.decision["a"] = 999
    first.strategy = "mutated"

    second = cache.get("groq", "m", _messages(), 0.0, None)
    assert second.decision["a"] == 1
    assert second.strategy == ""


def test_prefix_cache_expires():
    from app.llm.types import CompletionResult, TokenUsage

    cache = PrefixCache(ttl_seconds=0.01)
    result = CompletionResult(
        provider="groq",
        model="m",
        content="hi",
        usage=TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2, cost=0.0),
    )
    cache.set("groq", "m", _messages(), 0.0, None, result)
    time.sleep(0.02)
    assert cache.get("groq", "m", _messages(), 0.0, None) is None


# --- Compression (unit) ------------------------------------------------------


def test_normalize_whitespace_collapses_blank_runs_and_trailing_spaces():
    raw = "line one   \n\n\n\nline two\n\n\n"
    assert normalize_whitespace(raw) == "line one\n\nline two"


def test_cap_length_keeps_head_and_tail():
    text = "A" * 100
    capped = cap_length(text, 40)
    assert len(capped) <= 40 + len("\n...[compressed: 100 chars omitted]...\n")
    assert capped.startswith("A")
    assert capped.endswith("A")
    assert "compressed" in capped


def test_cap_length_noop_under_limit():
    assert cap_length("short", 100) == "short"


def test_compress_messages_does_not_mutate_input():
    original = [ChatMessage(role="user", content="a\n\n\n\nb")]
    compressed = compress_messages(original, max_chars=1000)
    assert original[0].content == "a\n\n\n\nb"
    assert compressed[0].content == "a\n\nb"


# --- Integration: cache wired into LLMRouter.complete -----------------------


@respx.mock
def test_complete_serves_second_identical_call_from_cache():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant"]
    settings.llm_cache_enabled = True

    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant")
    )

    async def _run():
        router = LLMRouter()
        try:
            first = await router.complete(_messages(), devil_mode=False)
            second = await router.complete(_messages(), devil_mode=False)
            return first, second
        finally:
            await router.close()

    first, second = asyncio.run(_run())

    assert route.call_count == 1  # second call served from cache
    assert first.content == second.content == "pong"
    assert first.decision["cache_hit"] is False
    assert second.decision["cache_hit"] is True


@respx.mock
def test_complete_bypasses_cache_when_disabled():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant"]
    settings.llm_cache_enabled = False

    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant")
    )

    async def _run():
        router = LLMRouter()
        try:
            await router.complete(_messages(), devil_mode=False)
            await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    asyncio.run(_run())

    assert route.call_count == 2  # cache disabled -> both hit the network
    settings.llm_cache_enabled = True  # reset shared singleton


@respx.mock
def test_complete_cache_is_specific_to_prompt_content():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant"]
    settings.llm_cache_enabled = True

    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant")
    )

    async def _run():
        router = LLMRouter()
        try:
            await router.complete(_messages("ping"), devil_mode=False)
            await router.complete(_messages("a different prompt"), devil_mode=False)
        finally:
            await router.close()

    asyncio.run(_run())

    assert route.call_count == 2  # distinct prompts never share a cache entry


@respx.mock
def test_complete_compresses_outbound_messages():
    settings = get_settings()
    settings.judgment_models = ["groq/llama-3.1-8b-instant"]
    settings.llm_max_prompt_chars = 20

    route = respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant")
    )

    async def _run():
        router = LLMRouter()
        try:
            await router.complete(_messages("x" * 500), devil_mode=False)
        finally:
            await router.close()

    asyncio.run(_run())

    sent_body = route.calls[0].request.content
    import json

    payload = json.loads(sent_body)
    sent_content = payload["messages"][0]["content"]
    assert len(sent_content) < 500
    assert "compressed" in sent_content

    settings.llm_max_prompt_chars = 8000  # reset shared singleton
