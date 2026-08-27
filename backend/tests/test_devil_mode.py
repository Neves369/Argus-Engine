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


def test_devil_mode_on_executes():
    get_settings().devil_mode = True

    async def _run() -> GraphState:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        return await Director().run(state)

    final = asyncio.run(_run())

    assert "execute" in _actions(final)
    assert final.stop_reason == "completed"


def test_devil_mode_requested_but_globally_disabled_simulates():
    get_settings().devil_mode = False

    async def _run() -> GraphState:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        return await Director().run(state)

    final = asyncio.run(_run())

    assert "execute" not in _actions(final)
    assert "simulate" in _actions(final)
