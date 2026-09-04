from __future__ import annotations

import hashlib
from pathlib import Path

CONTENT = b"hello evidence"


def _create_run_and_finding(client) -> tuple[int, int]:
    run = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    run_id = run.json()["id"]
    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    finding_id = findings[0]["id"]
    return run_id, finding_id


def test_attach_evidence(client):
    _, finding_id = _create_run_and_finding(client)

    response = client.post(
        f"/api/v1/findings/{finding_id}/evidence",
        files={"file": ("report.txt", CONTENT, "text/plain")},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["sha256"] == hashlib.sha256(CONTENT).hexdigest()
    assert body["size"] == len(CONTENT)
    assert body["mime"] == "text/plain"
    assert body["file_name"] == "report.txt"
    assert Path(body["file_path"]).exists()
