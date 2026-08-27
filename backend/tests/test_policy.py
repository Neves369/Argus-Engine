from __future__ import annotations


def test_policy(client):
    response = client.get("/policy")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "1.0.0"
    assert len(body["sha256"]) == 64
    assert "Argus Engine" in body["text"]
