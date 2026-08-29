from __future__ import annotations

import hashlib
import hmac
import os

from app.core.config import get_settings

COOKIE_NAME = "argus_session"


def _secret() -> bytes:
    settings = get_settings()
    key = settings.session_secret or settings.ui_password
    if not key:
        return b"argus-dev-insecure-secret"
    return key.encode("utf-8")


def create_session_token() -> str:
    """Return an HMAC-signed session token (nonce.signature)."""
    nonce = os.urandom(16).hex()
    signature = hmac.new(_secret(), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{nonce}.{signature}"


def verify_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    nonce, _, signature = token.partition(".")
    expected = hmac.new(_secret(), nonce.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
