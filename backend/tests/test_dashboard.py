from __future__ import annotations

import json


def _create_run(client, archetypes=None):
    return client.post(
        "/api/v1/runs",
        json={
            "target": {"name": "example.com"},
            "archetypes": archetypes or ["hermit", "justice"],
        },
    )


def test_trace_endpoint_returns_steps(client):
    resp = _create_run(client)
    assert resp.status_code == 201
    run_id = resp.json()["id"]

    trace = client.get(f"/api/v1/runs/{run_id}/trace")
    assert trace.status_code == 200
    body = trace.json()
    assert body["run_id"] == run_id
    steps = body["trace"]
    assert len(steps) >= 2
    assert steps[0]["node"] == "hermit"
    assert "duration_ms" in steps[0]
    assert "started_at" in steps[0]
    assert steps[-1]["node"] == "justice"


def test_trace_not_found(client):
    assert client.get("/api/v1/runs/99999/trace").status_code == 404


def test_sarif_export(client):
    resp = _create_run(client)
    run_id = resp.json()["id"]

    sarif = client.get(f"/api/v1/runs/{run_id}/export", params={"format": "sarif"})
    assert sarif.status_code == 200
    doc = json.loads(sarif.text)
    assert doc["version"] == "2.1.0"
    assert doc["runs"][0]["tool"]["driver"]["name"] == "Argus Engine"
    results = doc["runs"][0]["results"]
    assert len(results) >= 1
    assert all("ruleId" in r and "message" in r for r in results)


def test_dashboard_summary(client):
    _create_run(client)
    resp = client.get("/api/v1/dashboard/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["runs"]["total"] >= 1
    assert body["runs"]["by_status"].get("completed", 0) >= 1
    assert body["findings"]["total"] >= 1
    assert "costs" in body


def test_dashboard_runs(client):
    resp = _create_run(client)
    run_id = resp.json()["id"]

    rows = client.get("/api/v1/dashboard/runs")
    assert rows.status_code == 200
    data = rows.json()
    assert any(r["id"] == run_id and r["status"] == "completed" for r in data)
