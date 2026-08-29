from __future__ import annotations

import asyncio

from app.db.models import Run
from app.db.session import async_session_factory
from app.orchestration.state import GraphState


def _seed_pending_run(kind: str = "finding_review") -> int:
    state = GraphState(
        target={"name": "example.com"},
        findings=[
            {
                "id": "F-1",
                "title": "Signal from source for example.com",
                "confidence": 0.4,
                "status": "candidate",
                "requires_human_review": True,
            }
        ],
        pending_review={
            "id": "review-1",
            "kind": kind,
            "context": "Review candidate finding.",
            "proposal": {"id": "F-1"},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        next_agent="human_gate",
        human_gate_next="justice" if kind == "finding_review" else None,
    )

    async def _create() -> int:
        async with async_session_factory() as session:
            run = Run(status="pending_review", result=state.model_dump())
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run.id

    return asyncio.run(_create())


def test_review_api_approve_completes(client):
    run_id = _seed_pending_run("finding_review")

    resp = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"approval_id": "review-1", "approved": True, "note": "ok"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert body["result"].get("pending_review") is None

    report = client.get(f"/api/v1/runs/{run_id}/report").json()
    assert report["pending_review"] is None
    assert report["status"] == "completed"


def test_review_api_wrong_approval_id(client):
    run_id = _seed_pending_run("finding_review")

    resp = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"approval_id": "review-999", "approved": True},
    )
    assert resp.status_code == 422


def test_review_api_not_pending(client):
    run_id = (
        client.post(
            "/api/v1/runs",
            json={"target": {"name": "example.com"}, "archetypes": ["hermit", "justice"]},
        )
        .json()
        .get("id")
    )

    resp = client.post(
        f"/api/v1/runs/{run_id}/review",
        json={"approval_id": "review-1", "approved": True},
    )
    assert resp.status_code == 409
