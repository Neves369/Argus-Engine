from __future__ import annotations

import asyncio

import pytest

from app.core.config import get_settings
from app.db.models import Run
from app.db.session import async_session_factory
from app.orchestration.compose import validate_sequence
from app.orchestration.director import Director
from app.orchestration.state import GraphState
from app.services.run_executor import resume_run


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
    # No sources_service configured in this test -> no real signal -> no
    # findings fabricated. This is the correct, honest behavior: findings
    # only appear when a real, successfully-queried source justifies one
    # (see app.services.source_findings).
    assert final.findings == []


def test_director_runs_six_archetypes():
    archetypes = ["emperor", "fool", "hermit", "chariot", "magician", "justice"]

    async def _run() -> GraphState:
        director = Director(archetypes)
        return await director.run(GraphState(target={"name": "example.com"}))

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert len(final.history) == 6


def test_composition_run_stops_on_budget():
    """Composição respeita o orçamento do run: estourou, o pipeline desvia
    para a Justiça validar e fechar em vez de seguir a próxima carta."""
    async def _run() -> GraphState:
        state = GraphState(
            target={"name": "example.com"},
            budget_tokens=0,
            composition=["hermit", "justice"],
        )
        return await Director(["hermit", "justice"]).run(state)

    final = asyncio.run(_run())

    assert final.stop_reason == "budget"
    assert final.history[-1]["agent"] == "justice"


def test_resume_after_hitl_continues_composition_pipeline(client):
    """Retomada de um run de composição parado no HITL NÃO deve recair no
    supervisor (Imperador/time padrão): segue a sequência linear exata,
    da carta parada até a Justiça. É o bug do `resume_run` com
    `archetypes=None` (perdia a composição) sendo coberto de ponta a ponta.
    O fixture `client` garante que o startup do app criou as tabelas do banco.
    """
    get_settings().devil_mode = True

    async def _scenario():
        state = GraphState(
            target={"name": "example.com"},
            devil_mode=True,
            composition=["chariot", "justice"],
        )
        awaiting = await Director(["chariot", "justice"]).run(state)
        assert awaiting.stop_reason == "pending_review"

        async with async_session_factory() as session:
            run = Run(status="pending_review", result=awaiting.model_dump())
            session.add(run)
            await session.commit()
            await session.refresh(run)
            final = await resume_run(
                session,
                run,
                {"id": awaiting.pending_review["id"], "approved": True},
            )
        return final

    final = asyncio.run(_scenario())

    agents = [entry["agent"] for entry in final.history]
    assert agents == ["chariot", "justice"]
    assert final.pending_review is None
    assert final.stop_reason == "no_backend"


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
