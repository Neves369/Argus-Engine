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


def test_findings_are_rich(client, run_id):
    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    assert len(findings) >= 1
    for finding in findings:
        assert finding["severity"] in {"critical", "high", "medium", "low", "info"}
        assert finding["category"]
        assert finding["description"]
        assert finding["confidence"] >= 0
        assert isinstance(finding["cves"], list)
        assert isinstance(finding["known_exploits"], list)
        assert isinstance(finding["references"], list)


def test_result_findings_are_rich(client, run_id):
    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert len(run["result"]["findings"]) >= 1
    for finding in run["result"]["findings"]:
        assert finding["severity"] in {"critical", "high", "medium", "low", "info"}
        assert finding["category"]
        assert finding["description"]
        assert finding["remediation"]


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
    assert response.text.startswith("# Relatório de segurança")
    assert "Remediação" in response.text


def test_report(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/report")
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"] == run_id
    assert body["summary"]["total_findings"] >= 1
    assert "by_severity" in body["summary"]
    assert "observability" in body
    assert body["started_at"] is not None
    assert body["finished_at"] is not None
    assert isinstance(body["duration_ms"], int)
    assert isinstance(body["trace"], list)
    assert isinstance(body["history"], list)
    for finding in body["findings"]:
        assert "severity" in finding
        assert "cves" in finding
        assert "known_exploits" in finding
        assert "remediation" in finding


def test_export_bad_format(client, run_id):
    response = client.get(f"/api/v1/runs/{run_id}/export", params={"format": "xml"})
    assert response.status_code == 400
