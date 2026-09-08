from __future__ import annotations

import asyncio
import importlib

from cryptography.fernet import Fernet
from sqlalchemy import delete

from app.core.auth_overrides import clear_ui_password_override
from app.core.config import get_settings
from app.core.session import create_session_token, verify_session_token
from app.db.models import AppSetting
from app.db.session import async_session_factory


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


def _build_auth_client(monkeypatch, session_secret: str | None = "test-secret"):
    monkeypatch.setenv("UI_PASSWORD", "test-pass")
    if session_secret:
        monkeypatch.setenv("ARGUS_SESSION_SECRET", session_secret)
    else:
        monkeypatch.delenv("ARGUS_SESSION_SECRET", raising=False)
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


def test_login_rate_limit_blocks_after_max(monkeypatch):
    from app.api.v1 import auth as auth_mod

    client = _build_auth_client(monkeypatch)
    auth_mod._reset_login_attempts()
    with client:
        for _ in range(5):
            resp = client.post("/api/v1/auth/login", json={"password": "wrong"})
            assert resp.status_code == 401

        blocked = client.post("/api/v1/auth/login", json={"password": "wrong"})
        assert blocked.status_code == 429
        assert blocked.headers.get("Retry-After")

        # A senha correta também fica bloqueada enquanto a janela não expira.
        assert (
            client.post("/api/v1/auth/login", json={"password": "test-pass"}).status_code
            == 429
        )
    auth_mod._reset_login_attempts()
    get_settings.cache_clear()


def test_login_success_resets_limit(monkeypatch):
    from app.api.v1 import auth as auth_mod

    client = _build_auth_client(monkeypatch)
    auth_mod._reset_login_attempts()
    with client:
        for _ in range(4):
            assert (
                client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code
                == 401
            )
        # Login correto zera o contador do IP.
        assert (
            client.post("/api/v1/auth/login", json={"password": "test-pass"}).status_code
            == 200
        )
        assert (
            client.post("/api/v1/auth/login", json={"password": "wrong"}).status_code
            == 401
        )
    auth_mod._reset_login_attempts()
    get_settings.cache_clear()


async def _delete_ui_override() -> None:
    async with async_session_factory() as db:
        await db.execute(delete(AppSetting).where(AppSetting.key == "ui_password"))
        await db.commit()


def _enum_key() -> str:
    return Fernet.generate_key().decode()


def test_password_rotation(monkeypatch):
    monkeypatch.setenv("ARGUS_ENCRYPTION_KEY", _enum_key())
    from app.api.v1 import auth as auth_mod

    # sem ARGUS_SESSION_SECRET: a chave HMAC deriva da senha → rotação invalida
    # as sessões existentes.
    client = _build_auth_client(monkeypatch, session_secret=None)
    auth_mod._reset_login_attempts()
    try:
        with client:
            login = client.post("/api/v1/auth/login", json={"password": "test-pass"})
            assert login.status_code == 200

            wrong_current = client.post(
                "/api/v1/auth/password",
                json={"current_password": "errada", "new_password": "nova-forte-123"},
            )
            assert wrong_current.status_code == 401

            short = client.post(
                "/api/v1/auth/password",
                json={"current_password": "test-pass", "new_password": "curta"},
            )
            assert short.status_code == 422

            changed = client.post(
                "/api/v1/auth/password",
                json={"current_password": "test-pass", "new_password": "nova-forte-123"},
            )
            assert changed.status_code == 200
            body = changed.json()
            assert body["ok"] is True
            assert body["sessions_invalidated"] is True

            # Cookie antigo foi invalidado pela rotação.
            assert client.get("/api/v1/runs").status_code == 401

            # Senha antiga não funciona mais; a nova, sim.
            assert (
                client.post(
                    "/api/v1/auth/login", json={"password": "test-pass"}
                ).status_code
                == 401
            )
            fresh = client.post(
                "/api/v1/auth/login", json={"password": "nova-forte-123"}
            )
            assert fresh.status_code == 200

        # O override sobrevive à reinicialização do servidor (persistido cifrado).
        from app.services.app_settings import load_ui_password_override_from_db

        clear_ui_password_override()
        asyncio.run(load_ui_password_override_from_db())
        from app.core.auth_overrides import effective_ui_password

        assert effective_ui_password() == "nova-forte-123"
    finally:
        asyncio.run(_delete_ui_override())
        clear_ui_password_override()
        auth_mod._reset_login_attempts()
        get_settings.cache_clear()


def test_password_rotation_requires_encryption(monkeypatch):
    from app.api.v1 import auth as auth_mod

    client = _build_auth_client(monkeypatch)
    auth_mod._reset_login_attempts()
    with client:
        assert (
            client.post("/api/v1/auth/login", json={"password": "test-pass"}).status_code
            == 200
        )
        resp = client.post(
            "/api/v1/auth/password",
            json={"current_password": "test-pass", "new_password": "nova-forte-123"},
        )
        assert resp.status_code == 409
    auth_mod._reset_login_attempts()
    get_settings.cache_clear()
