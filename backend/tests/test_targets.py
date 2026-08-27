from __future__ import annotations


def test_create_and_list_target(client):
    response = client.post(
        "/api/v1/targets",
        json={"name": "example.com", "url": "https://example.com", "notes": "test"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "example.com"
    assert body["id"] == 1

    response = client.get("/api/v1/targets")
    assert response.status_code == 200
    targets = response.json()
    assert len(targets) >= 1


def test_get_target_not_found(client):
    response = client.get("/api/v1/targets/9999")
    assert response.status_code == 404


def test_run_rejects_out_of_scope_target(client):
    response = client.post("/api/v1/runs", json={"target": {"name": "evil.org"}})
    assert response.status_code == 403
