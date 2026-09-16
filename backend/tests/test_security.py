from __future__ import annotations

import pytest

from app.core.config import get_settings
from app.core.security import ScopeValidationError, validate_scope


def _set_scopes(monkeypatch, scopes):
    settings = get_settings()
    monkeypatch.setattr(settings, "allowed_scopes", scopes)


def test_validate_scope_allows_bare_host(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    assert validate_scope("example.com") == "example.com"


def test_validate_scope_allows_subdomain(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    assert validate_scope("api.example.com") == "api.example.com"


def test_validate_scope_allows_host_with_port(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    assert validate_scope("example.com:4280") == "example.com"


def test_validate_scope_allows_full_url_with_port(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    assert validate_scope("https://example.com:4280/") == "example.com"


def test_validate_scope_allows_full_url_with_path(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    assert validate_scope("http://www.example.com/lab") == "www.example.com"


def test_validate_scope_rejects_out_of_scope_host(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    with pytest.raises(ScopeValidationError):
        validate_scope("evil.org")


def test_validate_scope_rejects_out_of_scope_url(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    with pytest.raises(ScopeValidationError):
        validate_scope("https://evil.org:8443/")


def test_validate_scope_rejects_empty(monkeypatch):
    _set_scopes(monkeypatch, ["example.com"])
    with pytest.raises(ScopeValidationError):
        validate_scope("")


def test_validate_scope_allows_any_when_scopes_empty(monkeypatch):
    _set_scopes(monkeypatch, [])
    assert validate_scope("https://anything.example:9999/") == "anything.example"