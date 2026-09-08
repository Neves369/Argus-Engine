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
        validate_sequence(["hermit", "nope", "justice"])
    with pytest.raises(ValueError):
        validate_sequence(["hermit", "justice", "chariot"])
    with pytest.raises(ValueError):
        validate_sequence(["hermit"])
    # O Imperador não é carta no modelo universal — rege todo run.
    with pytest.raises(ValueError):
        validate_sequence(["emperor", "hermit", "justice"])


def test_validate_sequence_accepts_valid():
    assert validate_sequence(["hermit", "justice"]) == ["hermit", "justice"]


def test_director_runs_composition_supervised():
    """Composição roda supervisionada: o Imperador decide e pode repetir a
    carta até confiança suficiente, quando fecha pela Justiça."""
    async def _run() -> GraphState:
        director = Director(["hermit", "justice"])
        return await director.run(GraphState(target={"name": "example.com"}))

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert final.history[-1]["agent"] == "justice"
    agents = [e["agent"] for e in final.history if e["agent"] != "emperor"]
    assert agents[0] == "hermit"
    assert set(agents) <= {"hermit", "justice"}
    # Repetição é permitida: o Eremita roda até a confiança fechar o run.
    assert agents.count("hermit") >= 1
    # Sem sources_service configurado -> nenhum finding fabricado.
    assert final.findings == []


def test_composition_restricts_team():
    """As cartas jogadas restringem o time: o Imperador escala apenas as
    cartas escolhidas (nunca as que ficaram de fora da mesa)."""
    async def _run() -> GraphState:
        director = Director(["fool", "justice"])
        return await director.run(GraphState(target={"name": "example.com"}))

    final = asyncio.run(_run())

    workers = [e["agent"] for e in final.history if e["agent"] != "emperor"]
    assert {"fool", "justice"} <= set(workers)
    assert not {"hermit", "magician", "chariot"} & set(workers)
    assert final.history[-1]["agent"] == "justice"


def test_composition_run_stops_on_budget():
    """Composição respeita o orçamento do run: estourou, desvia para a
    Justiça validar e fechar em vez de seguir delegando."""
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


def test_resume_after_hitl_continues_composition_supervised(client):
    """Retomada de um run de composição parado no HITL mantém o time
    restrito às cartas jogadas (aquele com o Carro em Modo Diabo) e fecha
    pela Justiça. O fixture `client` garante que o startup do app criou as
    tabelas do banco."""
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

    workers = [e["agent"] for e in final.history if e["agent"] != "emperor"]
    assert "chariot" in workers
    assert not {"hermit", "fool", "magician"} & set(workers)
    assert final.history[-1]["agent"] == "justice"
    assert final.pending_review is None
    assert final.stop_reason == "no_backend"


def test_create_run_with_archetypes(client):
    response = client.post(
        "/api/v1/runs",
        json={
            "target": {"name": "example.com"},
            "archetypes": ["hermit", "justice"],
        },
    )
    assert response.status_code == 201


def test_create_run_invalid_archetypes(client):
    response = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com"}, "archetypes": ["hermit", "hermit", "justice"]},
    )
    assert response.status_code == 422

    emperor_response = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com"}, "archetypes": ["emperor", "hermit", "justice"]},
    )
    assert emperor_response.status_code == 422