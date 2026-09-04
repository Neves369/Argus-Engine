from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

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


# --- Orçamento por agente (Etapa 7) ----------------------------------------


def test_apply_llm_accumulates_per_agent_totals():
    from app.agents.builtin import _apply_llm

    state = GraphState()
    entry: dict = {"agent": "hermit"}
    update: dict = {}
    _apply_llm(entry, update, state, result=None, fallback_tokens=250)

    assert update["tokens_by_agent"] == {"hermit": 250}
    assert "cost_by_agent" not in update  # sem custo real no fallback offline

    # Segunda chamada do MESMO agente acumula sobre o estado já atualizado.
    state2 = state.model_copy(update=update)
    entry2: dict = {"agent": "hermit"}
    update2: dict = {}
    _apply_llm(entry2, update2, state2, result=None, fallback_tokens=250)
    assert update2["tokens_by_agent"] == {"hermit": 500}


def test_apply_llm_keeps_agents_separate():
    from app.agents.builtin import _apply_llm

    state = GraphState(tokens_by_agent={"hermit": 250})
    entry: dict = {"agent": "chariot"}
    update: dict = {}
    _apply_llm(entry, update, state, result=None, fallback_tokens=500)

    assert update["tokens_by_agent"] == {"hermit": 250, "chariot": 500}


def test_should_continue_ignores_per_agent_budget_when_disabled(monkeypatch):
    _set_settings(monkeypatch, budget_tokens_per_agent=0)
    state = GraphState(tokens_by_agent={"hermit": 999_999})
    decision = graph_mod.should_continue(state)
    assert decision != "stop"
    assert state.stop_reason is None


def test_should_continue_stops_when_next_agent_over_its_own_budget(monkeypatch):
    _set_settings(monkeypatch, budget_tokens_per_agent=1000)
    # route_after_director() picks "hermit" when devil_mode is off.
    state = GraphState(devil_mode=False, tokens_by_agent={"hermit": 1000})
    decision = graph_mod.should_continue(state)
    assert decision == "stop"
    assert state.stop_reason == "agent_budget"


def test_should_continue_per_agent_budget_does_not_affect_other_agents(monkeypatch):
    _set_settings(monkeypatch, budget_tokens_per_agent=1000)
    # chariot is way over, but the NEXT agent (hermit, devil_mode off) is fine.
    state = GraphState(devil_mode=False, tokens_by_agent={"chariot": 5000})
    decision = graph_mod.should_continue(state)
    assert decision != "stop"
    assert state.stop_reason is None


def test_should_continue_per_agent_cost_budget():
    from app.core import config as cfg_mod

    settings = cfg_mod.get_settings()
    original = settings.budget_cost_per_agent
    settings.budget_cost_per_agent = 0.05
    try:
        state = GraphState(devil_mode=False, cost_by_agent={"hermit": 0.05})
        decision = graph_mod.should_continue(state)
        assert decision == "stop"
        assert state.stop_reason == "agent_budget"
    finally:
        settings.budget_cost_per_agent = original


def test_justice_preserves_agent_budget_stop_reason():
    async def _run() -> dict:
        from app.agents import get_archetype

        state = GraphState(target={"name": "example.com"}, stop_reason="agent_budget")
        return await get_archetype("justice").run(state)

    result = asyncio.run(_run())
    assert result["stop_reason"] == "agent_budget"


# --- Compactação de saída de tools ("RTK ou equivalente", Etapa 7) --------


def test_compact_tool_output_drops_empty_values():
    from app.llm.compress import compact_tool_output

    raw = {"a": 1, "b": None, "c": "", "d": [], "e": {}, "f": 0, "g": False}
    assert compact_tool_output(raw) == {"a": 1, "f": 0, "g": False}


def test_compact_tool_output_recurses_into_nested_structures():
    from app.llm.compress import compact_tool_output

    raw = {
        "results": [
            {"name": "a", "note": None},
            {"name": "", "note": "kept"},
            {},
        ],
        "meta": {"empty_child": {}, "count": 2},
    }
    assert compact_tool_output(raw) == {
        "results": [{"name": "a"}, {"note": "kept"}],
        "meta": {"count": 2},
    }


def test_compact_tool_output_collapses_whitespace_in_strings():
    from app.llm.compress import compact_tool_output

    assert compact_tool_output("  a   b\n\nc  ") == "a b c"


def test_compact_tool_output_leaves_scalars_untouched():
    from app.llm.compress import compact_tool_output

    assert compact_tool_output(42) == 42
    assert compact_tool_output(3.14) == 3.14
    assert compact_tool_output(None) is None


@respx.mock
def test_tool_executor_compacts_json_http_body_when_enabled(monkeypatch):
    from app.tools import ToolExecutor, ToolRegistry, ToolSpec
    from app.tools.spec import ToolKind

    _set_settings(monkeypatch, tool_output_compression=True)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="api", kind=ToolKind.HTTP, url="http://tool-test.local/x", method="GET")
    )
    respx.get("http://tool-test.local/x").mock(
        return_value=Response(200, json={"data": {"score": 0, "note": None, "tags": []}})
    )

    result = asyncio.run(ToolExecutor(registry).execute("api", {}))
    assert result["body"] == '{"data":{"score":0}}'


@respx.mock
def test_tool_executor_leaves_http_body_raw_when_disabled(monkeypatch):
    from app.tools import ToolExecutor, ToolRegistry, ToolSpec
    from app.tools.spec import ToolKind

    _set_settings(monkeypatch, tool_output_compression=False)

    registry = ToolRegistry()
    registry.register(
        ToolSpec(name="api", kind=ToolKind.HTTP, url="http://tool-test2.local/x", method="GET")
    )
    respx.get("http://tool-test2.local/x").mock(
        return_value=Response(200, json={"data": {"score": 0, "note": None}})
    )

    result = asyncio.run(ToolExecutor(registry).execute("api", {}))
    assert "note" in result["body"]  # unmodified raw JSON text


def test_tool_executor_compacts_cli_output_when_enabled(monkeypatch):
    import sys

    from app.tools import ToolExecutor, ToolRegistry, ToolSpec
    from app.tools.spec import ToolKind

    _set_settings(monkeypatch, tool_output_compression=True)

    registry = ToolRegistry()
    registry.register(ToolSpec(name="py", kind=ToolKind.CLI, command=sys.executable, timeout=10.0))

    result = asyncio.run(
        ToolExecutor(registry).execute("py", {"args": ["-c", "print('ok')"]})
    )
    # stderr is empty on success -> dropped entirely when compression is on.
    assert "stderr" not in result
    assert result["stdout"] == "ok"
