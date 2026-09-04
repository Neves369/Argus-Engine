from __future__ import annotations

import importlib

from app.core.config import get_settings
from app.core.session import create_session_token, verify_session_token


def test_session_token_roundtrip():
    token = create_session_token()
    assert verify_session_token(token) is True
    assert verify_session_token(token + "x") is False
    assert verify_session_token(None) is False
    assert verify_session_token("not-a-token") is False


def test_require_auth_open_when_no_password():
    from app.api.deps import require_auth

    # Default settings have UI_PASSWORD unset -> guard is a no-op.
    require_auth(None)


def _build_auth_client(monkeypatch):
    monkeypatch.setenv("UI_PASSWORD", "test-pass")
    monkeypatch.setenv("ARGUS_SESSION_SECRET", "test-secret")
    get_settings.cache_clear()
    import app.main as main_mod

    importlib.reload(main_mod)
    from fastapi.testclient import TestClient

    return TestClient(main_mod.app)


def test_auth_flow(monkeypatch):
    client = _build_auth_client(monkeypatch)
    with client:
        # No session cookie yet -> protected routes require auth.
        assert client.get("/api/v1/runs").status_code == 401

        # Wrong password is rejected.
        assert client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code == 401

        # Correct password issues the session cookie.
        resp = client.post("/api/v1/auth/login", json={"password": "test-pass"})
        assert resp.status_code == 200
        assert resp.cookies.get("argus_session")

        # With the cookie, protected routes work and /me reports authenticated.
        assert client.get("/api/v1/runs").status_code == 200
        assert client.get("/api/v1/auth/me").json()["authenticated"] is True

        # Logout clears the cookie and re-protects the routes.
        assert client.post("/api/v1/auth/logout").status_code == 200
        assert client.get("/api/v1/runs").status_code == 401
    get_settings.cache_clear()
