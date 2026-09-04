from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.orchestration.director import Director
from app.orchestration.state import GraphState


def _actions(final: GraphState) -> list[str]:
    return [entry.get("action") for entry in final.history]


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
