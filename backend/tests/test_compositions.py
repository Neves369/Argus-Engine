from __future__ import annotations


def _create(client, name="grafo-a", archetypes=None, target=None, devil_mode=False):
    return client.post(
        "/api/v1/compositions",
        json={
            "name": name,
            "archetypes": archetypes or ["hermit", "justice"],
            "target": target or {"name": "example.com"},
            "devil_mode": devil_mode,
        },
    )


def test_create_and_get_composition(client):
    resp = _create(client, name="grafo-a")
    assert resp.status_code == 201
    body = resp.json()
    assert body["id"] > 0
    assert body["name"] == "grafo-a"
    assert body["config"]["archetypes"] == ["hermit", "justice"]
    assert body["config"]["devil_mode"] is False

    got = client.get(f"/api/v1/compositions/{body['id']}")
    assert got.status_code == 200
    assert got.json()["name"] == "grafo-a"


def test_list_compositions(client):
    _create(client, name="grafo-1")
    _create(client, name="grafo-2", archetypes=["fool", "chariot", "justice"])
    resp = client.get("/api/v1/compositions")
    assert resp.status_code == 200
    names = {c["name"] for c in resp.json()}
    assert {"grafo-1", "grafo-2"} <= names


def test_delete_composition(client):
    created = _create(client, name="grafo-del").json()
    resp = client.delete(f"/api/v1/compositions/{created['id']}")
    assert resp.status_code == 204
    assert client.get(f"/api/v1/compositions/{created['id']}").status_code == 404


def test_create_requires_justice_at_end(client):
    resp = _create(client, archetypes=["hermit", "fool"])
    assert resp.status_code == 422


def test_create_rejects_duplicate_archetypes(client):
    resp = _create(client, archetypes=["hermit", "hermit", "justice"])
    assert resp.status_code == 422


def test_create_rejects_unknown_archetype(client):
    resp = _create(client, archetypes=["dragon", "justice"])
    assert resp.status_code == 422


def test_execute_composition_creates_run(client):
    created = _create(client, name="grafo-exec", target={"name": "example.com"}).json()
    cid = created["id"]
    resp = client.post(f"/api/v1/compositions/{cid}/execute", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["run_id"] > 0
    assert body["status"] == "completed"

    runs = client.get("/api/v1/runs").json()
    assert any(r["id"] == body["run_id"] for r in runs)


def test_execute_rejects_out_of_scope_target(client):
    created = _create(client, target={"name": "evil.example.org"}).json()
    resp = client.post(f"/api/v1/compositions/{created['id']}/execute", json={})
    assert resp.status_code == 403


def test_composition_not_found(client):
    assert client.get("/api/v1/compositions/9999").status_code == 404
    assert client.post("/api/v1/compositions/9999/execute", json={}).status_code == 404
