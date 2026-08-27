from __future__ import annotations

import asyncio

import pytest

from app.agents import available_archetypes, get_archetype
from app.orchestration.state import GraphState

EXPECTED_ARCHETYPES = {"emperor", "hermit", "fool", "justice", "chariot", "magician"}


def test_all_archetypes_registered():
    assert set(available_archetypes()) == EXPECTED_ARCHETYPES


@pytest.mark.parametrize("key", sorted(EXPECTED_ARCHETYPES))
def test_archetype_runs(key: str):
    async def _run() -> dict:
        archetype = get_archetype(key)
        state = GraphState(target={"name": "example.com"})
        return await archetype.run(state)

    update = asyncio.run(_run())

    assert isinstance(update, dict)
    assert "history" in update
    assert isinstance(update["history"], list)
