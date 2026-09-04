from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from app.services.run_control import (
    clear_cancel,
    is_cancel_requested,
    request_cancel,
)


def _raw_connection():
    return sqlite3.connect("data/test.db")


def _insert_run(status: str) -> int:
    now = datetime.now(UTC).isoformat()
    con = _raw_connection()
    try:
        cur = con.execute(
            "INSERT INTO runs (status, created_at, started_at) VALUES (?, ?, ?)",
            (status, now, now),
        )
        con.commit()
        return int(cur.lastrowid)
    finally:
        con.close()


def _delete_run(run_id: int) -> None:
    con = _raw_connection()
    try:
        con.execute("DELETE FROM runs WHERE id = ?", (run_id,))
        con.commit()
    finally:
        con.close()


def test_run_control_cancel_flag():
    run_id = 1
    assert is_cancel_requested(run_id) is False
    request_cancel(run_id)
    assert is_cancel_requested(run_id) is True
    clear_cancel(run_id)
    assert is_cancel_requested(run_id) is False


def test_active_endpoint_reports_running_run(client):
    run_id = _insert_run("running")
    try:
        res = client.get("/api/v1/runs/active")
        assert res.status_code == 200
        body = res.json()
        assert body["active"] is True
        assert body["run_id"] == run_id
        assert body["status"] == "running"
    finally:
        _delete_run(run_id)


def test_active_endpoint_reports_none_when_idle(client):
    res = client.get("/api/v1/runs/active")
    assert res.status_code == 200
    assert res.json() == {"active": False, "run_id": None, "status": None}


def test_lock_blocks_create_run(client):
    run_id = _insert_run("running")
    try:
        res = client.post(
            "/api/v1/runs",
            json={"target": {"name": "example.com"}, "archetypes": ["hermit", "justice"]},
        )
        assert res.status_code == 409
    finally:
        _delete_run(run_id)


def test_lock_blocks_stream_run(client):
    run_id = _insert_run("running")
    try:
        res = client.get(
            "/api/v1/runs/stream",
            params={"target": "example.com", "archetypes": "hermit,justice"},
        )
        assert res.status_code == 409
    finally:
        _delete_run(run_id)


def test_lock_blocks_composition_execute(client):
    created = client.post(
        "/api/v1/compositions",
        json={
            "name": "lock-test",
            "archetypes": ["hermit", "justice"],
            "target": {"name": "example.com"},
        },
    )
    assert created.status_code == 201
    comp_id = created.json()["id"]

    run_id = _insert_run("running")
    try:
        res = client.post(f"/api/v1/compositions/{comp_id}/execute")
        assert res.status_code == 409
    finally:
        _delete_run(run_id)
        client.delete(f"/api/v1/compositions/{comp_id}")


def test_cancel_run_transitions_to_cancelled(client):
    run_id = _insert_run("running")
    try:
        res = client.post(f"/api/v1/runs/{run_id}/cancel")
        assert res.status_code == 200
        assert res.json()["run_status"] == "cancelled"

        run = client.get(f"/api/v1/runs/{run_id}").json()
        assert run["status"] == "cancelled"
        assert run["finished_at"] is not None
    finally:
        _delete_run(run_id)


def test_cancel_run_not_found(client):
    assert client.post("/api/v1/runs/999999/cancel").status_code == 404


def test_cancel_completed_run_conflicts(client):
    res = client.get(
        "/api/v1/runs/stream",
        params={"target": "example.com", "archetypes": "hermit,justice"},
    )
    assert res.status_code == 200

    runs = client.get("/api/v1/runs").json()
    run_id = runs[-1]["id"]
    assert client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 409


def test_stream_run_with_session_id(client):
    created = client.post(
        "/api/v1/compositions",
        json={
            "name": "stream-session",
            "archetypes": ["hermit", "justice"],
            "target": {"name": "example.com"},
        },
    )
    assert created.status_code == 201
    comp_id = created.json()["id"]

    try:
        res = client.get("/api/v1/runs/stream", params={"session_id": comp_id})
        assert res.status_code == 200
        assert "event: node" in res.text
        assert "event: done" in res.text
    finally:
        client.delete(f"/api/v1/compositions/{comp_id}")