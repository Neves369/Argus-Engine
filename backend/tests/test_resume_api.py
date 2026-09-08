from __future__ import annotations

import asyncio

from app.db.models import Run
from app.db.session import async_session_factory
from app.orchestration.director import Director
from app.orchestration.state import GraphState


def _partial_cancelled_state() -> dict:
    """Estado de um run de composição cancelado no meio do caminho: o
    Imperador já planejou e delegou o Eremita uma vez (confiança 0.4), e a
    retomada deve continuar a partir daí — não recomeçar do zero."""
    return GraphState(
        target={"name": "example.com"},
        composition=["hermit", "justice"],
        team=["hermit"],
        delegate_to="hermit",
        supervisor_rounds=1,
        confidence=0.4,
        history=[
            {
                "agent": "emperor",
                "action": "plan",
                "next_agent": "hermit",
                "objective": "Iniciar investigação com o agente escolhido.",
            },
            {
                "agent": "hermit",
                "action": "simulate",
                "findings": 0,
                "sources_consulted": 0,
                "scanned": False,
                "pages_observed": 0,
            },
        ],
        trace=[
            {
                "node": "emperor",
                "action": "plan",
                "duration_ms": 1,
                "tokens": 0,
                "cost": 0.0,
            },
            {
                "node": "hermit",
                "action": "simulate",
                "duration_ms": 1,
                "tokens": 250,
                "cost": 0.0,
            },
        ],
    ).model_dump()


async def _seed_run(status: str, result: dict | None) -> int:
    async with async_session_factory() as session:
        run = Run(status=status, result=result)
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run.id


def _seed_cancelled_run() -> int:
    return asyncio.run(_seed_run("cancelled", _partial_cancelled_state()))


def test_resume_cancelled_run_streams_to_completion(client):
    run_id = _seed_cancelled_run()

    response = client.get(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 200
    body = response.text
    assert "event: start" in body
    assert "event: node" in body
    assert "event: done" in body
    assert f'"run_id": {run_id}' in body

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "completed"
    assert run["finished_at"] is not None

    report = client.get(f"/api/v1/runs/{run_id}/report").json()
    assert report["status"] == "completed"
    assert report["resumable"] is False
    # O Eremita re-coleta na retomada e gera o finding real (fake crt.sh).
    assert report["summary"]["total_findings"] >= 1


def test_resume_continues_from_partial_state(client):
    """A retomada parte da última etapa (Eremita), não do Imperador: o
    histórico persistido não é re-gerado, apenas complementado."""
    run_id = _seed_cancelled_run()

    response = client.get(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 200

    report = client.get(f"/api/v1/runs/{run_id}/report").json()
    agents = [entry.get("agent") for entry in (report["history"] or [])]
    # Imperador e Eremita já estavam no estado persistido — a retomada
    # continuou de onde parou (o Eremita) e fechou na Justiça.
    assert agents[0] == "emperor"
    assert agents[1] == "hermit"
    assert agents[-1] == "justice"
    assert agents.index("hermit") < agents.index("justice")


def test_resume_rejects_completed_run(client):
    run_id = (
        client.post(
            "/api/v1/runs",
            json={"target": {"name": "example.com"}, "archetypes": ["hermit", "justice"]},
        )
        .json()
        .get("id")
    )

    response = client.get(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 409
    assert "não pode ser retomado" in response.json()["detail"]


def test_resume_rejects_run_without_persisted_state(client):
    run_id = asyncio.run(_seed_run("failed", None))

    response = client.get(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 409
    assert "estado persistido" in response.json()["detail"]


def test_resume_respects_active_run_lock(client):
    run_id = _seed_cancelled_run()
    # Um segundo run ativo (pending_review) trava a retomada concorrente.
    blocking = asyncio.run(
        _seed_run(
            "pending_review",
            GraphState(
                target={"name": "example.com"},
                pending_review={"id": "review-1", "kind": "x"},
            ).model_dump(),
        )
    )
    assert blocking > 0

    response = client.get(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 409


def test_resume_not_found(client):
    assert client.get("/api/v1/runs/99999/resume").status_code == 404


def test_report_flags_run_as_resumable(client):
    cancelled_id = _seed_cancelled_run()
    assert client.get(f"/api/v1/runs/{cancelled_id}/report").json()["resumable"] is True

    completed_id = (
        client.post(
            "/api/v1/runs",
            json={"target": {"name": "example.com"}, "archetypes": ["hermit", "justice"]},
        )
        .json()
        .get("id")
    )
    assert client.get(f"/api/v1/runs/{completed_id}/report").json()["resumable"] is False


def test_resume_kill_switch_active(client, monkeypatch):
    run_id = _seed_cancelled_run()

    def _kill_switch_active() -> bool:
        return True

    monkeypatch.setattr("app.api.v1.runs.is_kill_switch_active", _kill_switch_active)
    response = client.get(f"/api/v1/runs/{run_id}/resume")
    assert response.status_code == 423


def test_director_resume_agent_picks_entry(client):
    async def _entry(run_id: int) -> str:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            assert run is not None and run.result is not None
            director = Director((run.result or {}).get("composition"))
            return director.resume_agent(GraphState.model_validate(run.result))

    async def _seed(state: GraphState) -> int:
        async with async_session_factory() as session:
            run = Run(status="cancelled", result=state.model_dump())
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run.id

    with_next = asyncio.run(
        _seed(
            GraphState(
                target={"name": "example.com"},
                next_agent="hermit",
                composition=["hermit", "justice"],
            )
        )
    )
    with_team = asyncio.run(
        _seed(
            GraphState(
                target={"name": "example.com"}, composition=["hermit", "justice"]
            )
        )
    )
    default = asyncio.run(_seed(GraphState(target={"name": "example.com"})))

    assert asyncio.run(_entry(with_next)) == "hermit"
    assert asyncio.run(_entry(with_team)) == "hermit"
    assert asyncio.run(_entry(default)) == "emperor"