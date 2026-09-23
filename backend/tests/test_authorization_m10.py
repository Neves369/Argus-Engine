from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Run
from app.orchestration.state import GraphState
from app.services.export import run_report, run_report_markdown


def test_target_authorization_note_roundtrip(client):
    note = "Autorizado pelo time X (ticket ABC-123)"
    created = client.post(
        "/api/v1/targets",
        json={"name": "example.com", "authorization_note": note},
    )
    assert created.status_code == 201
    target_id = created.json()["id"]
    assert created.json()["authorization_note"] == note

    fetched = client.get(f"/api/v1/targets/{target_id}")
    assert fetched.status_code == 200
    assert fetched.json()["authorization_note"] == note


def _run(authorization_note: str | None = None) -> Run:
    result: dict = {
        "target": {"name": "example.com"},
        "scan": [{"target": "example.com", "depth": "quick", "auth_status": "skipped"}],
    }
    if authorization_note:
        result["target"]["authorization_note"] = authorization_note
    return Run(id=1, status="completed", result=result, created_at=datetime.now(UTC))


def test_report_exposes_authorization():
    note = "Autorizado pelo time X (ticket ABC-123)"
    report = run_report(_run(note), [])
    assert report["authorization"] == note


def test_report_without_authorization_is_none():
    report = run_report(_run(), [])
    assert report["authorization"] is None


def test_markdown_includes_authorization():
    note = "Autorizado pelo time X"
    md = run_report_markdown(_run(note), [])
    assert f"- **Autorização:** {note}" in md


def test_markdown_omits_authorization_when_absent():
    md = run_report_markdown(_run(), [])
    assert "Autorização" not in md


def test_state_trims_authorization_note():
    state = GraphState(target={"name": "example.com", "authorization_note": "  nota  "})
    assert state.target["authorization_note"] == "nota"
