from __future__ import annotations

import asyncio

from app.agents import get_archetype
from app.core.config import get_settings
from app.core.security import activate_kill_switch, deactivate_kill_switch
from app.orchestration.director import Director
from app.orchestration.state import GraphState
from app.tools.spec import ToolKind, ToolSpec


def _actions(final: GraphState) -> list[str]:
    return [entry.get("action") for entry in final.history]


class _FakeExecutor:
    """Executor de teste: registra chamadas e devolve sucesso, sem rede."""

    def __init__(self, specs, on_execute=None):
        self._specs = specs
        self.calls: list[tuple] = []
        self.on_execute = on_execute

    @property
    def registry(self):
        return self

    def specs(self):
        return self._specs

    async def execute(self, name, params=None, *, devil_mode=False):
        self.calls.append((name, params, devil_mode))
        if self.on_execute is not None:
            self.on_execute(name)
        return {"tool": name, "status_code": 200, "ok": True}


def _spec(name: str, destructive: bool = False) -> ToolSpec:
    return ToolSpec(name=name, kind=ToolKind.CLI, command="echo", destructive=destructive)


async def _run_approved(executor) -> tuple[dict, _FakeExecutor]:
    """Aprova o HITL e roda o Carro com o executor injetado."""
    state = GraphState(target={"name": "example.com"}, devil_mode=True)
    awaiting = await get_archetype("chariot").run(state)
    state2 = state.model_copy(deep=True)
    state2.set_tool_executor(executor)
    state2.pending_review = awaiting["pending_review"]
    state2.human_decision = {"id": awaiting["pending_review"]["id"], "approved": True}
    return await get_archetype("chariot").run(state2), executor


def test_devil_mode_off_simulates():
    get_settings().devil_mode = False

    async def _run() -> GraphState:
        state = GraphState(target={"name": "example.com"}, devil_mode=False)
        return await Director().run(state)

    final = asyncio.run(_run())

    assert "simulate" in _actions(final)
    assert "execute" not in _actions(final)
    assert final.stop_reason == "completed"


def test_devil_mode_on_requires_human_approval():
    get_settings().devil_mode = True

    async def _run() -> GraphState:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        return await Director().run(state)

    final = asyncio.run(_run())

    # The destructive action halts awaiting operator approval.
    assert "execute" not in _actions(final)
    assert final.pending_review is not None
    assert final.pending_review["kind"] == "destructive_action"
    assert final.stop_reason == "pending_review"


def test_devil_mode_executes_after_approval():
    """No real destructive-execution backend ships with Argus Engine by design —
    once approved, Chariot honestly reports "no_backend" instead of fabricating
    a success. See ADR on Devil Mode scope."""
    get_settings().devil_mode = True

    async def _run() -> GraphState:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        awaiting = await Director().run(state)
        state2 = awaiting.model_copy(deep=True)
        state2.human_decision = {
            "id": awaiting.pending_review["id"],
            "approved": True,
            "note": "approved by operator",
        }
        return await Director().run_from(state2, state2.next_agent or "chariot")

    final = asyncio.run(_run())

    assert "no_backend" in _actions(final)
    assert "execute" not in _actions(final)
    assert final.stop_reason == "no_backend"
    assert final.pending_review is None


def test_devil_mode_requested_but_globally_disabled_simulates():
    get_settings().devil_mode = False

    async def _run() -> GraphState:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        return await Director().run(state)

    final = asyncio.run(_run())

    assert "execute" not in _actions(final)
    assert "simulate" in _actions(final)


# ---------------------------------------------------------------------------
# Backend de execução controlada (M5) — tools da allowlist após aprovação
# ---------------------------------------------------------------------------


def test_devil_executes_allowlisted_tools_after_approval():
    settings = get_settings()
    original = (settings.devil_mode, settings.devil_max_rate, settings.devil_allowed_tools)
    settings.devil_mode = True
    settings.devil_max_rate = 0
    settings.devil_allowed_tools = ["tool_a", "tool_b"]
    try:
        executor = _FakeExecutor([_spec("tool_a"), _spec("tool_b"), _spec("other")])
        result, executor = asyncio.run(_run_approved(executor))
    finally:
        settings.devil_mode, settings.devil_max_rate, settings.devil_allowed_tools = original

    entry = result["history"][-1]
    assert entry["action"] == "executed"
    assert entry["mode"] == "devil"
    assert entry["tools_tried"] == 2
    assert entry["devil_probes_done"] == 2
    assert [s["tool"] for s in entry["devil_steps"]] == ["tool_a", "tool_b"]
    assert all(step["outcome"] == "ok" for step in entry["devil_steps"])
    # Fora da allowlist não roda; todas as chamadas passam devil_mode=True.
    assert [c[0] for c in executor.calls] == ["tool_a", "tool_b"]
    assert all(c[2] is True for c in executor.calls)
    assert result["stop_reason"] == "devil_completed"
    assert result["devil_probes_done"] == 2


def test_devil_runs_destructive_tool_from_allowlist():
    settings = get_settings()
    original = (settings.devil_mode, settings.devil_max_rate, settings.devil_allowed_tools)
    settings.devil_mode = True
    settings.devil_max_rate = 0
    settings.devil_allowed_tools = ["danger"]
    try:
        executor = _FakeExecutor([_spec("danger", destructive=True)])
        result, executor = asyncio.run(_run_approved(executor))
    finally:
        settings.devil_mode, settings.devil_max_rate, settings.devil_allowed_tools = original

    entry = result["history"][-1]
    assert entry["action"] == "executed"
    assert entry["devil_steps"][0]["destructive"] is True
    assert executor.calls[0][2] is True  # devil_mode=True libera o gate


def test_devil_respects_max_probes():
    settings = get_settings()
    original = (
        settings.devil_mode,
        settings.devil_max_rate,
        settings.devil_allowed_tools,
        settings.devil_max_probes,
    )
    settings.devil_mode = True
    settings.devil_max_rate = 0
    settings.devil_allowed_tools = ["tool_a", "tool_b", "tool_c"]
    settings.devil_max_probes = 2
    try:
        executor = _FakeExecutor([_spec("tool_a"), _spec("tool_b"), _spec("tool_c")])
        result, executor = asyncio.run(_run_approved(executor))
    finally:
        (
            settings.devil_mode,
            settings.devil_max_rate,
            settings.devil_allowed_tools,
            settings.devil_max_probes,
        ) = original

    entry = result["history"][-1]
    assert entry["action"] == "executed"
    assert entry["devil_probes_done"] == 2
    assert [s["tool"] for s in entry["devil_steps"]] == ["tool_a", "tool_b"]
    assert result["stop_reason"] == "devil_limits"


def test_devil_kill_switch_stops_execution():
    settings = get_settings()
    original = (settings.devil_mode, settings.devil_max_rate, settings.devil_allowed_tools)
    settings.devil_mode = True
    settings.devil_max_rate = 0
    settings.devil_allowed_tools = ["tool_a", "tool_b", "tool_c"]
    try:
        executor = _FakeExecutor(
            [_spec("tool_a"), _spec("tool_b"), _spec("tool_c")],
            on_execute=lambda _n: activate_kill_switch(),
        )
        result, executor = asyncio.run(_run_approved(executor))
    finally:
        deactivate_kill_switch()
        settings.devil_mode, settings.devil_max_rate, settings.devil_allowed_tools = original

    entry = result["history"][-1]
    assert entry["action"] == "executed"
    assert entry["devil_probes_done"] == 1
    assert [s["tool"] for s in entry["devil_steps"]] == ["tool_a"]
    assert result["stop_reason"] == "devil_kill_switch"


def test_devil_empty_allowlist_falls_back_no_backend():
    settings = get_settings()
    original = (settings.devil_mode, settings.devil_allowed_tools)
    settings.devil_mode = True
    settings.devil_allowed_tools = []
    try:
        executor = _FakeExecutor([_spec("tool_a")])
        result, _executor = asyncio.run(_run_approved(executor))
    finally:
        settings.devil_mode, settings.devil_allowed_tools = original

    entry = result["history"][-1]
    assert entry["action"] == "no_backend"
    assert result["stop_reason"] == "no_backend"
