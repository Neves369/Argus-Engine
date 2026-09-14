"""Scope-aware HTTP tools for the Chariot (Etapa M2).

These tools give the executor real, non-destructive HTTP/session probes:
``http_request``, ``form_discover``, ``session_login`` and ``http_header_probe``.
They reuse the active-scanning controls (``SCAN_*``) — rate limit, timeout,
body cap, user-agent, extra headers/cookies and robots.txt — plus a per-host
cookie jar, so a ``session_login`` result is transparently reused by later
probes against the same host.

Every request is preceded by scope validation (``ALLOWED_SCOPES``) and a
kill-switch check; a blocked attempt is logged and raised as a
``ToolExecutionError``. Nothing here sends a payload or performs an action
beyond a GET/POST form submission within the authorized scope.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin, urlparse

from app.core.security import is_kill_switch_active, validate_scope
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.login import login_payload, select_login_form
from app.scanning.parsers import parse_html
from app.scanning.robots import RobotsRules
from app.tools.executor import ToolExecutionError

logger = logging.getLogger(__name__)

_PROBE_HEADERS = (
    "server",
    "content-security-policy",
    "strict-transport-security",
    "x-frame-options",
    "x-content-type-options",
    "referrer-policy",
    "permissions-policy",
    "x-powered-by",
    "access-control-allow-origin",
    "set-cookie",
)

_MISSING = object()


def build_http_tool_handler() -> HttpToolHandler:
    """Instantiate the scope-aware HTTP handler from ``SCAN_*`` settings."""
    from app.core.config import get_settings

    settings = get_settings()
    client = ScanHTTPClient(
        rate_limit=settings.scan_rate_limit,
        timeout=settings.scan_request_timeout,
        max_body_bytes=settings.scan_max_body_bytes,
        user_agent=settings.scan_user_agent,
        extra_headers=settings.scan_extra_headers,
        cookies=settings.scan_cookies,
    )
    return HttpToolHandler(
        client=client,
        respect_robots=settings.scan_respect_robots,
        login_url=settings.scan_login_url,
        login_username=settings.scan_login_username,
        login_password=settings.scan_login_password,
    )


class HttpToolHandler:
    """Dispatch the ``kind: scanner`` tools against the authorized target."""

    def __init__(
        self,
        *,
        client: ScanHTTPClient | None = None,
        respect_robots: bool = True,
        login_url: str = "",
        login_username: str = "",
        login_password: str = "",
    ) -> None:
        self._client = client or ScanHTTPClient()
        self._respect_robots = respect_robots
        self._login_url = login_url
        self._login_username = login_username
        self._login_password = login_password
        self._robots_cache: dict[str, RobotsRules | None] = {}

    async def handle(self, handler: str, params: dict[str, Any]) -> dict[str, Any]:
        if handler == "form_discover":
            return await self.form_discover(params)
        if handler == "http_header_probe":
            return await self.http_header_probe(params)
        if handler == "session_login":
            return await self.session_login(params)
        return await self.http_request(params)

    async def http_request(self, params: dict[str, Any]) -> dict[str, Any]:
        """Fetch a URL (GET by default; POST when ``method``/``data`` given)."""
        url = self._require_url(params)
        method = str(params.get("method") or "GET").upper()
        if method == "POST":
            data = params.get("data") if isinstance(params.get("data"), dict) else {}
            page = await self._fetch(url, method="POST", data=data)
        else:
            page = await self._fetch(url)
        return {
            "tool": "http_request",
            "url": page.url,
            "status_code": page.status_code,
            "headers": page.headers,
            "body": page.body,
            "body_truncated": page.body_truncated,
        }

    async def form_discover(self, params: dict[str, Any]) -> dict[str, Any]:
        """List the forms (action/method/fields) of a URL."""
        url = self._require_url(params)
        page = await self._fetch(url)
        forms = parse_html(page.url, page.body)["forms"]
        return {
            "tool": "form_discover",
            "url": page.url,
            "status_code": page.status_code,
            "forms": [
                {
                    "action": form.action,
                    "method": form.method,
                    "fields": [
                        {"name": fld.name, "type": fld.type} for fld in form.fields
                    ],
                }
                for form in forms
            ],
        }

    async def http_header_probe(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return the security-relevant response headers of a URL."""
        url = self._require_url(params)
        page = await self._fetch(url)
        headers = {k: v for k, v in page.headers.items() if k in _PROBE_HEADERS}
        return {
            "tool": "http_header_probe",
            "url": page.url,
            "status_code": page.status_code,
            "headers": headers,
        }

    async def session_login(self, params: dict[str, Any]) -> dict[str, Any]:
        """Submit the configured login form and reuse the session cookie.

        Credentials come from ``SCAN_LOGIN_*`` settings (never from tool
        params, never logged). A failed/absent login does NOT raise — it is
        reported as an auditable note, matching the scanner's behaviour.
        """
        if not (self._login_url and self._login_username and self._login_password):
            return {"tool": "session_login", "note": "login não configurado"}

        url = self._login_url
        self._assert_in_scope(url)
        try:
            page = await self._client.get_page(url)
        except ScanError as exc:  # noqa: BLE001 - transcribed into the result
            return {"tool": "session_login", "note": f"página indisponível: {exc}"}

        form = select_login_form(parse_html(page.url, page.body)["forms"])
        if form is None:
            return {
                "tool": "session_login",
                "note": "nenhum form com campo de senha encontrado",
            }

        action = urljoin(page.url, form.action or page.url)
        data = login_payload(form, self._login_username, self._login_password)
        try:
            if form.method == "post":
                response = await self._client.post_page(action, data)
            else:
                from urllib.parse import urlencode

                response = await self._client.get_page(urljoin(action, "?" + urlencode(data)))
        except ScanError as exc:  # noqa: BLE001
            return {"tool": "session_login", "note": f"submissão falhou: {exc}"}

        if response.status_code >= 400:
            return {
                "tool": "session_login",
                "note": f"login falhou (status {response.status_code})",
            }
        return {"tool": "session_login", "note": "sessão estabelecida", "url": action}

    async def _fetch(
        self,
        url: str,
        *,
        method: str = "GET",
        data: dict[str, str] | None = None,
    ):
        self._assert_in_scope(url)
        if self._respect_robots and method == "GET":
            blocked = await self._robots_blocked(url)
            if blocked:
                raise ToolExecutionError(f"Blocked by robots.txt: {blocked}")
        try:
            if method == "POST":
                return await self._client.post_page(url, data or {})
            return await self._client.get_page(url)
        except ScanError as exc:
            raise ToolExecutionError(f"request failed: {exc}") from exc

    @staticmethod
    def _require_url(params: dict[str, Any]) -> str:
        url = str(params.get("url") or params.get("target") or "").strip()
        if not url:
            raise ToolExecutionError("tool requires a 'url' (or 'target') parameter")
        if not url.startswith(("http://", "https://")):
            url = "https://" + url.lstrip("/")
        return url

    def _assert_in_scope(self, url: str) -> None:
        host = urlparse(url).netloc
        if is_kill_switch_active():
            raise ToolExecutionError("Kill switch is active")
        try:
            validate_scope(host)
        except ValueError as exc:
            logger.info(
                "tool blocked out of scope", extra={"url": url, "host": host}
            )
            raise ToolExecutionError(
                f"Target {host} is not in the authorized scope"
            ) from exc

    async def _robots_blocked(self, url: str) -> str | None:
        host = urlparse(url).netloc
        rules = self._robots_cache.get(host, _MISSING)
        if rules is _MISSING:
            rules = await self._load_robots(host)
            self._robots_cache[host] = rules
        if rules is None:
            return None
        path = urlparse(url).path or "/"
        return None if rules.is_allowed(path) else "robots disallow"

    async def _load_robots(self, host: str) -> RobotsRules | None:
        robots_url = urljoin(f"https://{host}/", "robots.txt")
        try:
            page = await self._client.fetch_no_rate_limit(robots_url)
        except ScanError:
            return None
        if page.status_code not in (200, 204):
            return None
        return RobotsRules.parse(page.body, user_agent=self._client.user_agent)
