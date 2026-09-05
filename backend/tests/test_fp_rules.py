from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.fp_rules import normalize_pattern


@pytest.fixture(autouse=True)
def _clean_fp_rules():
    yield
    from sqlite3 import connect

    con = connect("data/test.db")
    try:
        con.execute("DELETE FROM fp_rules")
        con.commit()
    except Exception:
        pass
    finally:
        con.close()


@pytest.fixture()
def run_id(client) -> int:
    response = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    assert response.status_code == 201
    return response.json()["id"]


def _findings(client, run_id):
    return client.get(f"/api/v1/runs/{run_id}/findings").json()


# ---- normalize_pattern (puro) ----


def test_normalize_pattern_rejects_trivial():
    assert normalize_pattern(None) is None
    assert normalize_pattern("") is None
    assert normalize_pattern("abc") is None


def test_normalize_pattern_normalizes_case_and_whitespace():
    assert normalize_pattern("  Subdomains FOUND  ") == "subdomains found"


# ---- API: gestão de regras ----


def test_fp_rules_crud(client):
    created = client.post("/api/v1/findings/fp-rules", json={"pattern": "banner noise"})
    assert created.status_code == 201
    rule = created.json()
    assert rule["pattern"] == "banner noise"
    assert rule["source"] == "manual"
    assert rule["enabled"] is True
    assert rule["hit_count"] == 0

    listed = client.get("/api/v1/findings/fp-rules").json()
    assert any(r["id"] == rule["id"] for r in listed)

    toggled = client.patch(f"/api/v1/findings/fp-rules/{rule['id']}", json={"enabled": False})
    assert toggled.status_code == 200
    assert toggled.json()["enabled"] is False

    deleted = client.delete(f"/api/v1/findings/fp-rules/{rule['id']}")
    assert deleted.status_code == 204
    listed = client.get("/api/v1/findings/fp-rules").json()
    assert all(r["id"] != rule["id"] for r in listed)


def test_fp_rule_create_rejects_trivial_pattern(client):
    response = client.post("/api/v1/findings/fp-rules", json={"pattern": "abc"})
    assert response.status_code == 422


def test_fp_rule_delete_missing_returns_404(client):
    response = client.delete("/api/v1/findings/fp-rules/999999")
    assert response.status_code == 404


def test_store_create_dedupes(client):
    first = client.post("/api/v1/findings/fp-rules", json={"pattern": "dup noise"})
    second = client.post("/api/v1/findings/fp-rules", json={"pattern": "  DUP NOISE "})
    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]


# ---- loop de aprendizado ----


def test_human_fp_learns_rule(client, run_id):
    finding = _findings(client, run_id)[0]

    response = client.patch(
        f"/api/v1/findings/{finding['id']}", json={"status": "false_positive"}
    )
    assert response.status_code == 200

    rules = client.get("/api/v1/findings/fp-rules").json()
    learned = [r for r in rules if r["source"] == "learned"]
    assert any(
        r["pattern"] == finding["title"].lower() and r["source_finding_id"] == finding["id"]
        for r in learned
    )


def test_learning_respects_fp_learning_off(client, run_id, monkeypatch):
    finding = _findings(client, run_id)[0]

    monkeypatch.setattr(
        "app.services.fp_rules.get_settings",
        lambda: SimpleNamespace(fp_learning=False),
    )

    client.patch(
        f"/api/v1/findings/{finding['id']}", json={"status": "false_positive"}
    )

    rules = client.get("/api/v1/findings/fp-rules").json()
    assert all(r["source"] != "learned" for r in rules)


def test_learned_rule_suppresses_similar_finding_and_counts_hits(client, run_id):
    finding = _findings(client, run_id)[0]

    client.patch(
        f"/api/v1/findings/{finding['id']}", json={"status": "false_positive"}
    )

    second_run = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    assert second_run.status_code == 201
    similar = next(
        f for f in _findings(client, second_run.json()["id"])
        if f["title"] == finding["title"] and f["status"] == "candidate"
    )

    response = client.post(f"/api/v1/findings/{similar['id']}/validate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "false_positive"
    assert body["requires_human_review"] is False

    rules = client.get("/api/v1/findings/fp-rules").json()
    learned = [r for r in rules if r["source"] == "learned"]
    assert any(r["hit_count"] >= 1 for r in learned)


def test_disabled_rule_stops_suppressing(client, run_id):
    finding = _findings(client, run_id)[0]

    client.patch(
        f"/api/v1/findings/{finding['id']}", json={"status": "false_positive"}
    )
    rules = client.get("/api/v1/findings/fp-rules").json()
    rule = next(r for r in rules if r["source"] == "learned")
    client.patch(f"/api/v1/findings/fp-rules/{rule['id']}", json={"enabled": False})

    second_run = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    assert second_run.status_code == 201
    similar = next(
        f for f in _findings(client, second_run.json()["id"])
        if f["title"] == finding["title"] and f["status"] == "candidate"
    )

    response = client.post(f"/api/v1/findings/{similar['id']}/validate")
    assert response.status_code == 200
    assert response.json()["status"] != "false_positive"