from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import deactivate_kill_switch


@pytest.fixture(autouse=True)
def _reset_kill_switch():
    deactivate_kill_switch()
    get_settings.cache_clear()
    yield
    deactivate_kill_switch()
    get_settings.cache_clear()


def test_kill_switch_status_inactive(client):
    resp = client.get("/api/v1/operate/kill-switch")
    assert resp.status_code == 200
    assert resp.json() == {"active": False, "source": "none"}


def test_kill_switch_activate_runtime(client):
    resp = client.post(
        "/api/v1/operate/kill-switch", json={"reason": "incidente em andamento"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"active": True, "source": "runtime"}

    status = client.get("/api/v1/operate/kill-switch").json()
    assert status == {"active": True, "source": "runtime"}

    # Idempotente: já ativo via runtime, POST continua 200.
    again = client.post("/api/v1/operate/kill-switch", json={"reason": "de novo"})
    assert again.status_code == 200
    assert again.json() == {"active": True, "source": "runtime"}


def test_kill_switch_requires_reason(client):
    resp = client.post("/api/v1/operate/kill-switch", json={"reason": ""})
    assert resp.status_code == 422

    blank = client.post("/api/v1/operate/kill-switch", json={})
    assert blank.status_code == 422


def test_kill_switch_rejects_env_config(client, monkeypatch):
    monkeypatch.setenv("KILL_SWITCH", "true")
    get_settings.cache_clear()

    status = client.get("/api/v1/operate/kill-switch").json()
    assert status == {"active": True, "source": "env"}

    # Fail-closed: ativo via env não pode ser desativado nem re-ativado.
    resp = client.post("/api/v1/operate/kill-switch", json={"reason": "tentar"})
    assert resp.status_code == 409


def test_kill_switch_requires_auth(monkeypatch):
    monkeypatch.setenv("UI_PASSWORD", "test-pass")
    monkeypatch.setenv("ARGUS_SESSION_SECRET", "test-secret")
    get_settings.cache_clear()

    import importlib

    import app.main as main_mod

    importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    with TestClient(main_mod.app) as c:
        assert c.get("/api/v1/operate/kill-switch").status_code == 401
        assert (
            c.post("/api/v1/operate/kill-switch", json={"reason": "x"}).status_code
            == 401
        )
    get_settings.cache_clear()