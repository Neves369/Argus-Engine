from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

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


def _sources_service() -> Any:
    async def query(name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "status": "simulated",
            "source": name,
            "data": {"note": "stub"},
            "fetched_at": "2026-01-01T00:00:00+00:00",
        }

    return SimpleNamespace(
        available_sources=lambda: ["shodan", "cve"],
        get_source=lambda name: SimpleNamespace(target_kind="any", query_param="q"),
        query=query,
    )


def _run(key: str, state: GraphState) -> dict:
    return asyncio.run(get_archetype(key).run(state))


def test_sources_field_persisted_and_service_not_serialized():
    state = GraphState(target={"name": "example.com"})
    state.set_sources_service(_sources_service())

    dump = state.model_dump()
    assert "sources" in dump
    assert dump["sources"] == []
    assert "sources_service" not in dump


def test_hermit_queries_sources_when_service_provided():
    state = GraphState(target={"name": "example.com"})
    state.set_sources_service(_sources_service())

    update = _run("hermit", state)

    assert len(update["sources"]) >= 1
    assert update["sources"][0]["status"] == "simulated"
    assert update["history"][-1]["sources_consulted"] == 2


def test_agents_without_service_return_no_sources():
    for key in ("hermit", "fool", "justice", "magician"):
        update = _run(key, GraphState(target={"name": "example.com"}))
        assert len(update.get("sources", [])) == 0
