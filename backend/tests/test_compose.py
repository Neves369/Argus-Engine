from __future__ import annotations

import asyncio

import pytest

from app.orchestration.compose import validate_sequence
from app.orchestration.director import Director
from app.orchestration.state import GraphState


def test_validate_sequence_rejects_invalid():
    with pytest.raises(ValueError):
        validate_sequence([])
    with pytest.raises(ValueError):
        validate_sequence(["emperor", "emperor", "justice"])
    with pytest.raises(ValueError):
        validate_sequence(["emperor", "nope", "justice"])
    with pytest.raises(ValueError):
        validate_sequence(["emperor", "hermit"])


def test_validate_sequence_accepts_valid():
    assert validate_sequence(["emperor", "hermit", "justice"]) == [
        "emperor",
        "hermit",
        "justice",
    ]


def test_director_runs_custom_pipeline():
    async def _run() -> GraphState:
        director = Director(["emperor", "hermit", "justice"])
        return await director.run(GraphState(target={"name": "example.com"}))

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert len(final.history) == 3
    assert len(final.findings) == 1


def test_director_runs_six_archetypes():
    archetypes = ["emperor", "fool", "hermit", "chariot", "magician", "justice"]

    async def _run() -> GraphState:
        director = Director(archetypes)
        return await director.run(GraphState(target={"name": "example.com"}))

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert len(final.history) == 6


def test_create_run_with_archetypes(client):
    response = client.post(
        "/api/v1/runs",
        json={
            "target": {"name": "example.com"},
            "archetypes": ["emperor", "hermit", "justice"],
        },
    )
    assert response.status_code == 201


def test_create_run_invalid_archetypes(client):
    response = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com"}, "archetypes": ["emperor", "hermit"]},
    )
    assert response.status_code == 422
