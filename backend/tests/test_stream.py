from __future__ import annotations


def test_stream_run(client):
    response = client.get("/api/v1/runs/stream", params={"target": "example.com"})
    assert response.status_code == 200
    body = response.text
    assert "event: node" in body
    assert "event: done" in body


def test_stream_run_rejects_out_of_scope(client):
    response = client.get("/api/v1/runs/stream", params={"target": "evil.org"})
    assert response.status_code == 403


def test_stream_persists_run_and_findings(client):
    response = client.get("/api/v1/runs/stream", params={"target": "example.com"})
    assert response.status_code == 200

    runs = client.get("/api/v1/runs").json()
    assert len(runs) >= 1
    run_id = runs[-1]["id"]

    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    assert len(findings) >= 1
