from __future__ import annotations


def test_stream_run(client):
    response = client.get("/api/v1/runs/stream", params={"target": "example.com"})
    assert response.status_code == 200
    body = response.text
    assert "event: node" in body
    assert "event: done" in body


def test_stream_run_start_event_carries_run_id(client):
    response = client.get(
        "/api/v1/runs/stream", params={"target": "example.com", "archetypes": "hermit,justice"}
    )
    assert response.status_code == 200
    start_line = response.text.split("event: done")[0]
    assert "event: start" in start_line
    assert "run_id" in start_line


def test_stream_run_parses_comma_separated_archetypes(client):
    response = client.get(
        "/api/v1/runs/stream",
        params={"target": "example.com", "archetypes": "hermit,justice"},
    )
    assert response.status_code == 200
    body = response.text
    assert '"node": "hermit"' in body
    assert '"node": "justice"' in body
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


def test_stream_sse_robustness_fields(client):
    response = client.get("/api/v1/runs/stream", params={"target": "example.com"})
    assert response.status_code == 200
    body = response.text

    # Reconexão do navegador e ids de evento para retomada ordenada.
    assert "retry: 3000" in body
    assert "\nid: " in body

    # Cada evento nomeado traz seu campo id antes de data:.
    start_block = body.split("event: node")[0]
    assert "id: " in start_block
    assert "event: start" in start_block

