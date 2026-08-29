from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from app.agents import get_archetype
from app.core.config import get_settings
from app.orchestration.state import GraphState


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")


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


def _run(archetype_key: str, state: GraphState) -> dict:
    return asyncio.run(get_archetype(archetype_key).run(state))


def _fallback_env(monkeypatch):
    for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@respx.mock
def test_hermit_uses_llm_result_and_tracks_real_usage(monkeypatch):
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant")
    )

    state = GraphState(target={"name": "example.com"})
    result = _run("hermit", state)

    assert result["tokens_used"] == 1500
    assert result["cost"] > 0
    entry = result["history"][-1]
    assert entry["reasoning"] == "pong"
    assert entry["decision"]["mode"] == "judgment"
    assert result["findings"][-1]["severity"] in {"critical", "high", "medium", "low", "info"}
    assert result["findings"][-1]["cves"] == []


def test_hermit_falls_back_deterministic_without_api_key(monkeypatch):
    _fallback_env(monkeypatch)

    state = GraphState(target={"name": "example.com"})
    result = _run("hermit", state)

    assert result["tokens_used"] == 250
    assert "cost" not in result
    entry = result["history"][-1]
    assert "reasoning" not in entry
    assert entry["tokens"] == 250


@respx.mock
def test_hermit_falls_back_on_provider_error():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=Response(500, text="boom")
    )
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(500, text="boom")
    )

    state = GraphState(target={"name": "example.com"})
    result = _run("hermit", state)

    assert result["tokens_used"] == 250
    assert "reasoning" not in result["history"][-1]


@respx.mock
def test_chariot_requires_approval_then_executes():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.3-70b-versatile")
    )

    get_settings().devil_mode = True

    state = GraphState(target={"name": "example.com"}, devil_mode=True)

    # First pass: halted awaiting operator approval (no execution yet).
    result = _run("chariot", state)
    assert result["pending_review"]["kind"] == "destructive_action"

    # Approve, then re-run with the decision applied.
    state2 = state.model_copy(deep=True)
    state2.pending_review = result["pending_review"]
    state2.human_decision = {"id": result["pending_review"]["id"], "approved": True}
    result = _run("chariot", state2)

    entry = result["history"][-1]
    assert entry["action"] == "execute"
    assert result["findings"][-1]["title"].startswith("Executed action")


@respx.mock
def test_justice_uses_judgment_pool():
    respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
        return_value=_ok_response("llama-3.1-8b-instant")
    )

    state = GraphState(target={"name": "example.com"})
    result = _run("justice", state)

    assert result["stop_reason"] == "completed"
    assert result["history"][-1]["decision"]["mode"] == "judgment"


def test_offline_run_stays_deterministic(monkeypatch):
    _fallback_env(monkeypatch)

    state = GraphState(target={"name": "example.com"})
    result = _run("emperor", state)

    entry = result["history"][-1]
    assert entry["action"] == "plan"
    assert entry["mode"] == "simulate"
