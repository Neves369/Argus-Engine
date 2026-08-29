from __future__ import annotations

from app.core.config import Settings


def test_encryption_key_loaded_from_argus_env(monkeypatch):
    """O campo encryption_key deve ler ARGUS_ENCRYPTION_KEY do ambiente/.env."""
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    monkeypatch.setenv("ARGUS_ENCRYPTION_KEY", "4wle-key-0123=enjump=jbk=")

    s = Settings(_env_file=None)
    assert s.encryption_key == "4wle-key-0123=enjump=jbk="


def test_encryption_key_empty_when_unset(monkeypatch):
    monkeypatch.delenv("ARGUS_ENCRYPTION_KEY", raising=False)
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)

    s = Settings(_env_file=None)
    assert s.encryption_key == ""