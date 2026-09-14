from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import ScopeValidationError, validate_scope


def _allow(monkeypatch, *scopes: str) -> None:
    monkeypatch.setattr(get_settings(), "allowed_scopes", list(scopes))


def test_scope_accepts_host_with_port(monkeypatch):
    _allow(monkeypatch, "pentest-ground.com")
    assert validate_scope("pentest-ground.com:4280") == "pentest-ground.com"


def test_scope_accepts_full_url_with_port_and_path(monkeypatch):
    _allow(monkeypatch, "pentest-ground.com")
    assert validate_scope("http://pentest-ground.com:4280/login.php") == "pentest-ground.com"


def test_scope_accepts_subdomain(monkeypatch):
    _allow(monkeypatch, "example.com")
    assert validate_scope("sub.example.com") == "sub.example.com"


def test_scope_rejects_host_with_port_out_of_scope(monkeypatch):
    _allow(monkeypatch, "example.com")
    with pytest.raises(ScopeValidationError):
        validate_scope("evil.org:8080")


def test_scope_rejects_empty_target(monkeypatch):
    _allow(monkeypatch, "example.com")
    with pytest.raises(ScopeValidationError):
        validate_scope("")
