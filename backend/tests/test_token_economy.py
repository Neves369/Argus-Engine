from __future__ import annotations

import asyncio

import pytest

import app.core.config as cfg
from app.llm.compress import caveman_compress, compress_history, compress_messages
from app.llm.types import ChatMessage
from app.orchestration import graph as graph_mod
from app.orchestration.state import GraphState


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    cfg.get_settings.cache_clear()
    yield
    cfg.get_settings.cache_clear()


def _set_settings(monkeypatch, **kwargs):
    for key, value in kwargs.items():
        monkeypatch.setenv(key.upper(), str(value))
    cfg.get_settings.cache_clear()


def test_caveman_compress_strips_filler_and_collapses_spaces():
    text = "Please analyze the target and report any findings that you see."
    out = caveman_compress(text)
    assert "Please" not in out
    assert " the " not in out
    assert " and " not in out
    # Intenção preservada: palavras de conteúdo continuam.
    assert "analyze" in out
    assert "target" in out
    assert "report" in out
    assert "findings" in out
    assert "  " not in out


def test_compress_history_keeps_head_and_tail():
    history = [{"i": n} for n in range(12)]
    out = compress_history(history, keep_first=1, keep_last=3)
    assert len(out) == 4
    assert out[0] == {"i": 0}
    assert out[-3:] == [{"i": 9}, {"i": 10}, {"i": 11}]


def test_compress_history_noop_when_short():
    history = [{"i": n} for n in range(3)]
    out = compress_history(history, keep_first=1, keep_last=8)
    assert out == history


def test_compress_messages_applies_caveman():
    messages = [ChatMessage(role="user", content="Could you please analyze the host?")]
    out = compress_messages(messages, caveman=True)
    assert "Could you please" not in out[0].content
    assert "analyze" in out[0].content


def test_should_continue_sets_budget_stop_reason():
    state = GraphState(budget_tokens=10, tokens_used=10)
    assert graph_mod.should_continue(state) == "stop"
    assert state.stop_reason == "budget"


def test_should_continue_sets_confidence_stop_reason():
    state = GraphState(confidence=0.99)
    assert graph_mod.should_continue(state) == "stop"
    assert state.stop_reason == "confidence"


def test_should_continue_routes_when_within_budget():
    state = GraphState()
    decision = graph_mod.should_continue(state)
    assert decision != "stop"
    assert state.stop_reason is None


def test_node_wrapper_compresses_history_when_enabled(monkeypatch):
    _set_settings(
        monkeypatch, history_compression=True, history_keep_last=2, caveman_prompts=False
    )
    captured: dict[str, int] = {}

    async def fake(state: GraphState) -> dict:
        captured["len"] = len(state.history)
        return {}

    node = graph_mod._provisioned(fake, None)
    long_history = [{"i": n} for n in range(20)]
    state = GraphState(history=long_history)
    asyncio.run(node(state))
    # head(1) + tail(2) = 3; o agente enxerga o histórico já comprimido.
    assert captured["len"] == 3
    assert len(state.history) == 3


def test_node_wrapper_leaves_history_when_disabled(monkeypatch):
    _set_settings(monkeypatch, history_compression=False)
    captured: dict[str, int] = {}

    async def fake(state: GraphState) -> dict:
        captured["len"] = len(state.history)
        return {}

    node = graph_mod._provisioned(fake, None)
    long_history = [{"i": n} for n in range(20)]
    state = GraphState(history=long_history)
    asyncio.run(node(state))
    assert captured["len"] == 20
