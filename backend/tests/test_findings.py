from __future__ import annotations

import pytest


@pytest.fixture()
def run_id(client) -> int:
    response = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    assert response.status_code == 201
    return response.json()["id"]


def test_run_persists_findings(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/findings")
    assert response.status_code == 200
    findings = response.json()
    assert len(findings) >= 1
    assert findings[0]["status"] == "candidate"
    assert findings[0]["run_id"] == run_id


def test_run_persists_decisions(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/decisions")
    assert response.status_code == 200
    decisions = response.json()
    assert len(decisions) >= 3
    actions = {d["action"] for d in decisions}
    assert "plan" in actions
    assert "validate" in actions


def test_finding_lifecycle_transition(client, run_id):
    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    finding_id = findings[-1]["id"]

    response = client.patch(f"/api/v1/findings/{finding_id}", json={"status": "validated"})
    assert response.status_code == 409

    client.post(
        f"/api/v1/findings/{finding_id}/evidence",
        files={"file": ("report.txt", b"evidence", "text/plain")},
    )
    response = client.post(f"/api/v1/findings/{finding_id}/validate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validated"
    assert body["validated_at"] is not None

    response = client.patch(f"/api/v1/findings/{finding_id}", json={"status": "candidate"})
    assert response.status_code == 409


def test_finding_invalid_status_rejected(client, run_id):
    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    finding_id = findings[0]["id"]
    response = client.patch(f"/api/v1/findings/{finding_id}", json={"status": "bogus"})
    assert response.status_code == 422


def test_export_json(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/export", params={"format": "json"})
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_export_markdown(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/export", params={"format": "markdown"})
    assert response.status_code == 200
    assert response.text.startswith("# Findings")


def test_export_bad_format(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/export", params={"format": "xml"})
    assert response.status_code == 400
