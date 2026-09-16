"""Builtin M2 tools: safe, in-scope HTTP re-verification primitives.

These are the Carro's hands for re-probing scan leads (ROADMAP Etapa 15/M2).
They are strictly non-destructive re-observations: GET on pages the scan
already touched, form discovery on those pages, and optional header re-check.
Subjects REMARKS of ``docs/adr/0006-active-scanning.md``: every request goes
through ``ALLOWED_SCOPES`` validation and the kill-switch, uses a per-executor
session jar (shared ``ScanHTTPClient``), applies the scan rate limit/timeout,
and logs structurally. Credentials are never echoed: session_login returns
only the cookie *names* it set, never the values, and never the password.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from app.core.config import get_settings
from app.core.security import is_kill_switch_active, validate_scope
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.parsers import analyze_headers, parse_html
from app.scanning.service import _login_payload, _select_login_form

logger = logging.getLogger(__name__)


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class BuiltinToolError(RuntimeError):
    """Raised when a builtin M2 tool is blocked (scope, kill-switch, params)."""


_HANDLERS: dict[str, Any] = {}


def builtin_handler(name: str):
    """Register a builtin handler (``http_request``, ``session_login``, ...)."""

    def _decorate(func):
        _HANDLERS[name] = func
        return func

    return _decorate


def get_builtin_handler(name: str):
    try:
        return _HANDLERS[name]
    except KeyError:
        raise KeyError(f"Unknown builtin handler: {name}") from None


class BuiltinTools:
    """In-scope, non-destructive verification tools sharing one session jar."""

    def __init__(self, client: ScanHTTPClient | None = None) -> None:
        self._client = client or ScanHTTPClient()

    async def run(
        self, name: str, params: dict[str, Any] | None
    ) -> dict[str, Any]:
        handler = get_builtin_handler(name)
        return await handler(self, params or {})

    def _require_scope(self, url: str) -> None:
        """Fail closed: out-of-scope or kill-switched targets are blocked."""
        if is_kill_switch_active():
            raise BuiltinToolError("Kill switch is active")
        try:
            validate_scope(url)
        except ValueError as exc:
            raise BuiltinToolError(f"Out of scope: {exc}") from exc

    async def _get_page(self, url: str) -> dict[str, Any]:
        self._require_scope(url)
        try:
            page = await self._client.get_page(url)
        except ScanError:
            raise
        snippet = ""
        if page.body:
            snippet = " ".join(page.body.split())[:200]
        return {
            "url": page.url,
            "status_code": page.status_code,
            "final_url": page.final_url,
            "content_type": page.content_type,
            "snippet": snippet,
            "observed_at": _utcnow(),
        }

    @property
    def client(self) -> ScanHTTPClient:
        return self._client


@builtin_handler("http_request")
async def _http_request(builtins: BuiltinTools, params: dict[str, Any]) -> dict[str, Any]:
    """Re-fetch one URL in scope (GET by default). No payload, no parameters."""
    url = str(params.get("url") or "").strip()
    if not url:
        raise BuiltinToolError("http_request requires a target url")
    result = await builtins._get_page(url)
    result["tool"] = "http_request"
    result["ok"] = result["status_code"] < 400
    return result


@builtin_handler("session_login")
async def _session_login(builtins: BuiltinTools, params: dict[str, Any]) -> dict[str, Any]:
    """Submit a login form once and keep the session for the rest of the run.

    Returns only the cookie names stored in the jar — never values, and never
    the submitted credentials. Failure degrades to ``ok=False`` (an audited
    note), it does not raise a hard error.
    """
    settings = get_settings()
    login_url = str(params.get("login_url") or settings.scan_login_url or "").strip()
    username = str(params.get("username") or settings.scan_login_username or "").strip()
    password = str(params.get("password") or settings.scan_login_password or "").strip()
    if not (login_url and username and password):
        raise BuiltinToolError(
            "session_login requires login_url + username + password (or SCAN_LOGIN_*)"
        )
    builtins._require_scope(login_url)
    try:
        page = await builtins.client.get_page(login_url)
    except ScanError as exc:
        return {"tool": "session_login", "ok": False, "reason": f"login page unreachable: {exc}"}
    form = _select_login_form(parse_html(page.url, page.body)["forms"])
    if form is None:
        return {
            "tool": "session_login",
            "ok": False,
            "reason": "no login form with password field found",
        }
    action = urljoin(page.url, form.action or page.url)
    data = _login_payload(form, username, password)
    try:
        if form.method == "post":
            response = await builtins.client.post_page(action, data)
        else:
            joined = urljoin(action, "?" + urlencode(data))
            response = await builtins.client.get_page(joined)
    except ScanError as exc:
        return {"tool": "session_login", "ok": False, "reason": f"login failed: {exc}"}
    cookie_names = builtins.client.session_cookie_names(urlparse(login_url).netloc)
    return {
        "tool": "session_login",
        "ok": response.status_code < 400,
        "status_code": response.status_code,
        "auth_status": "success" if response.status_code < 400 else "failed",
        "auth_cookie_names": cookie_names,
        "url": login_url,
    }


@builtin_handler("form_discover")
async def _form_discover(builtins: BuiltinTools, params: dict[str, Any]) -> dict[str, Any]:
    """Discover editable forms on a URL the scan already touched."""
    url = str(params.get("url") or "").strip()
    if not url:
        raise BuiltinToolError("form_discover requires a target url")
    builtins._require_scope(url)
    try:
        page = await builtins.client.get_page(url)
    except ScanError:
        raise
    parsed = parse_html(page.url, page.body)
    forms = []
    for form in parsed["forms"]:
        fields = [fld.name for fld in form.fields if fld.name]
        sensitive_names = [
            fld.name
            for fld in form.fields
            if fld.name and fld.type in ("password", "file")
        ]
        forms.append(
            {
                "action": form.action or urlparse(page.url).path or "/",
                "method": form.method.upper(),
                "fields": fields,
                "sensitive_field_names": sensitive_names,
            }
        )
    return {
        "tool": "form_discover",
        "url": page.url,
        "status_code": page.status_code,
        "ok": page.status_code < 400,
        "form_count": len(forms),
        "forms": forms,
        "observed_at": _utcnow(),
    }


@builtin_handler("header_reprobe")
async def _header_reprobe(builtins: BuiltinTools, params: dict[str, Any]) -> dict[str, Any]:
    """Re-fetch one URL and report the response headers (misconfig re-proof)."""
    url = str(params.get("url") or "").strip()
    if not url:
        raise BuiltinToolError("header_reprobe requires a target url")
    builtins._require_scope(url)
    try:
        page = await builtins.client.get_page(url)
    except ScanError:
        raise
    headers = analyze_headers(page.headers or {})
    return {
        "tool": "header_reprobe",
        "url": page.url,
        "status_code": page.status_code,
        "ok": page.status_code < 400,
        "missing_security_headers": headers.get("missing_security_headers", []),
        "observed_at": _utcnow(),
    }