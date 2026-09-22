from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from app.core.security import is_kill_switch_active, validate_scope
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.fingerprint import fingerprint
from app.scanning.login import login_payload, select_login_form
from app.scanning.parsers import parse_html
from app.scanning.robots import RobotsRules
from app.scanning.spec import TargetPage

logger = logging.getLogger(__name__)


class ScanBlockedError(RuntimeError):
    """Raised when the scan is not permitted (kill-switch / out of scope)."""


@dataclass
class ScanReport:
    """Auditable outcome of an active scan against one target."""

    target: str
    pages: list[TargetPage] = field(default_factory=list)
    robots_respected: bool = True
    urls_skipped_by_robots: int = 0
    note: str | None = None
    auth: str | None = None
    auth_status: str | None = None
    auth_cookies: list[str] = field(default_factory=list)
    depth: str | None = None
    sessions: list[dict[str, Any]] = field(default_factory=list)
    anon_probe: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "robots_respected": self.robots_respected,
            "urls_skipped_by_robots": self.urls_skipped_by_robots,
            "note": self.note,
            "auth": self.auth,
            "auth_status": self.auth_status,
            "auth_cookies": list(self.auth_cookies),
            "depth": self.depth,
            "sessions": list(self.sessions),
            "anon_probe": list(self.anon_probe),
            "pages": [p.to_dict() for p in self.pages],
        }


class ScanService:
    """Coordinates active scanning within the authorized scope.

    Enforces, in order, the mandatory controls of
    ``docs/adr/0006-active-scanning.md``:

    #. scope validation (``ALLOWED_SCOPES``) — no request without a validated
       target;
    #. kill-switch — a running scan is halted before the next request;
    #. ``robots.txt`` (self-imposed restriction, ``SCAN_RESPECT_ROBOTS``);
    #. per-target rate limiting and per-request timeout (``SCAN_RATE_LIMIT`` /
       ``SCAN_REQUEST_TIMEOUT``) — handled by ``ScanHTTPClient``;
    #. every request is logged structurally.
    """

    def __init__(
        self,
        *,
        client: ScanHTTPClient | None = None,
        respect_robots: bool = True,
        max_pages: int = 10,
        depth: str | None = None,
        login_url: str = "",
        login_username: str = "",
        login_password: str = "",
    ) -> None:
        self._client = client or ScanHTTPClient()
        self._respect_robots = respect_robots
        self._max_pages = max(1, int(max_pages))
        self._depth = self._resolve_depth(depth)
        self._login_url = login_url
        self._login_username = login_username
        self._login_password = login_password

    def _resolve_depth(self, depth: str | None) -> str:
        """Effective scan depth: explicit value wins, else derived from scope.

        ``deep`` when the page budget is large enough for a full crawl of a
        mid-size application; otherwise ``quick``. Kept on the report so the
        operator knows what kind of run produced it (M2 gating: the Carro
        re-probes leads on ``deep`` runs).
        """
        if depth:
            return "deep" if str(depth).lower().startswith("deep") else "quick"
        return "deep" if self._max_pages >= 20 else "quick"

    async def scan(
        self, target: dict[str, Any], *, max_pages: int | None = None
    ) -> ScanReport:
        target_name = str((target or {}).get("name") or "")
        target_url = str((target or {}).get("url") or "")
        try:
            validate_scope(target_name)
            if target_url.strip():
                validate_scope(target_url)
        except ValueError as exc:
            raise ScanBlockedError(str(exc)) from exc

        if is_kill_switch_active():
            raise ScanBlockedError("Kill switch is active")

        derived = not str((target or {}).get("url") or "").strip()
        candidates = self._base_candidates(target)

        report = ScanReport(
            target=target_name,
            robots_respected=self._respect_robots,
            depth=self._depth,
        )
        await self._authenticate(report)
        override = self._max_pages if max_pages is None else max(1, int(max_pages))
        session = "user" if report.auth_status == "success" else "anon"
        for base_url in candidates:
            attempt = await self._crawl(base_url, max_pages=override, session=session)
            report.pages = attempt.pages
            report.urls_skipped_by_robots += attempt.urls_skipped_by_robots
            if attempt.robots_respected is not None:
                report.robots_respected = attempt.robots_respected
            if attempt.pages:
                report.note = attempt.note
                self._finalize_sessions(report, session)
                if report.auth_status == "success":
                    report.anon_probe = await self._anonymous_baseline(candidates)
                return report
            # No page reachable under this scheme (e.g. https rejected):
            # fall back to the next candidate only when the scheme was derived.
            if not derived and attempt.note:
                report.note = attempt.note
                break

        if not report.pages:
            report.note = (
                "Nenhuma página acessível retornou conteúdo dentro dos "
                "controles de escopo."
            )
        self._finalize_sessions(report, session)
        return report

    def _base_candidates(self, target: dict[str, Any]) -> list[str]:
        """Candidate base URLs: explicit url first, else https then http."""
        name = str(target.get("name") or "").strip()
        url = str(target.get("url") or "").strip()
        if url:
            if not url.startswith(("http://", "https://")):
                url = f"http://{url}"
            return [url.rstrip("/") + "/"]
        return [f"https://{name}/", f"http://{name}/"]

    async def _authenticate(self, report: ScanReport) -> None:
        """Submit the target's login form once and reuse the session cookies.

        Fills ``report.auth`` (note), ``report.auth_status``
        (``skipped|attempted|success|failed``) and ``report.auth_cookies``
        (cookie *names* only — never values, so the report stays auditable and
        redacted). A failed/partial login does NOT block the scan — the crawl
        proceeds unauthenticated and the outcome is recorded/auditable.
        """
        if not (self._login_url and self._login_username and self._login_password):
            report.auth_status = "skipped"
            return
        report.auth_status = "attempted"
        try:
            page = await self._client.get_page(self._login_url)
        except ScanError as exc:  # noqa: BLE001 - transcribed into the report
            logger.warning("scan login: page unreachable", extra={"reason": str(exc)})
            report.auth_status = "failed"
            report.auth = "login configurado mas página indisponível"
            return

        form = select_login_form(parse_html(page.url, page.body)["forms"])
        if form is None:
            report.auth_status = "failed"
            report.auth = "login configurado mas nenhum form com campo de senha encontrado"
            return

        action = urljoin(page.url, form.action or page.url)
        data = login_payload(form, self._login_username, self._login_password)
        try:
            if form.method == "post":
                response = await self._client.post_page(action, data)
            else:
                joined = urljoin(action, "?" + urlencode(data))
                response = await self._client.get_page(joined)
        except ScanError as exc:  # noqa: BLE001
            logger.warning("scan login: submission failed", extra={"reason": str(exc)})
            report.auth_status = "failed"
            report.auth = "login configurado mas a submissão falhou"
            return

        if response.status_code >= 400:
            report.auth_status = "failed"
            report.auth = f"login falhou (status {response.status_code})"
            return
        report.auth_status = "success"
        report.auth = "login dinâmico aplicado"
        report.auth_cookies = self._client.session_cookie_names(
            urlparse(self._login_url).netloc
        )

    def _finalize_sessions(self, report: ScanReport, session: str) -> None:
        """Label which session(s) observed the crawl (M7: session awareness).

        ``session`` is the channel the crawl actually ran under: ``user`` when
        the dynamic login succeeded, ``anon`` otherwise (no login configured,
        skipped, or a failed login that degraded to anonymous). The report
        carries the session metadata so findings can state, for example, when
        a route was only reachable once authenticated.
        """
        if session == "user":
            report.sessions = [
                {
                    "name": "user",
                    "auth_status": "success",
                    "auth": report.auth,
                    "auth_cookies": list(report.auth_cookies),
                    "page_count": len(report.pages),
                }
            ]
        else:
            report.sessions = [
                {
                    "name": "anon",
                    "auth_status": report.auth_status or "skipped",
                    "auth": report.auth,
                    "auth_cookies": [],
                    "page_count": len(report.pages),
                }
            ]

    async def _anonymous_baseline(self, candidates: list[str]) -> list[dict[str, Any]]:
        """Re-observe the base URLs without the session jar (M7-P0).

        A single anonymous GET per candidate on a *fresh* client — the 
        contrast with the authenticated crawl grounds a ``visível apenas na
        sessão user`` finding. Runs only after a successful login and only for
        the base URL(s), so request overhead stays minimal.
        """
        client = self._new_client()
        probe: list[dict[str, Any]] = []
        for base_url in candidates:
            try:
                page = await client.get_page(base_url)
            except ScanError:
                continue
            probe.append(
                {
                    "url": base_url,
                    "status_code": page.status_code,
                    "final_url": page.url,
                }
            )
        return probe

    def _new_client(self) -> ScanHTTPClient:
        """A fresh anonymous client with the same settings (empty session jar)."""
        from app.core.config import get_settings

        settings = get_settings()
        return ScanHTTPClient(
            rate_limit=settings.scan_rate_limit,
            timeout=settings.scan_request_timeout,
            max_body_bytes=settings.scan_max_body_bytes,
            user_agent=settings.scan_user_agent,
            extra_headers=settings.scan_extra_headers,
            cookies=settings.scan_cookies,
        )

    async def _crawl(
        self, base_url: str, *, max_pages: int | None = None, session: str = "anon"
    ) -> ScanReport:
        """BFS crawl of same-host pages bounded by ``max_pages`` (or the
        instance default when omitted — ``deep`` runs may override per call)."""
        limit = max(1, int(max_pages)) if max_pages is not None else self._max_pages
        robots = (
            await self._load_robots(base_url) if self._respect_robots else RobotsRules.allow_all()
        )
        attempt = ScanReport(
            target=urlparse(base_url).netloc,
            robots_respected=self._respect_robots,
        )
        visited: list[str] = []
        queue: list[str] = [base_url]
        base_host = urlparse(base_url).netloc

        while queue and len(visited) < limit:
            url = queue.pop(0)
            if url in visited:
                continue
            host = urlparse(url).netloc
            if host != base_host:
                continue
            if not robots.is_allowed(urlparse(url).path or "/"):
                attempt.urls_skipped_by_robots += 1
                continue
            visited.append(url)
            try:
                page = await self._client.get_page(url)
            except ScanError:
                continue
            page.tech = fingerprint(page)
            parsed = parse_html(page.url, page.body)
            page.links = parsed["links"]
            page.forms = parsed["forms"]
            page.session = session
            attempt.pages.append(page)
            queue.extend(page.links)

        if attempt.pages:
            attempt.note = None
        else:
            attempt.note = f"Sem conteúdo acessível em {base_url} dentro dos controles de escopo."
        return attempt

    async def _load_robots(self, base_url: str) -> RobotsRules:
        robots_url = urljoin(base_url, "robots.txt")
        try:
            page = await self._client.fetch_no_rate_limit(robots_url)
        except ScanError:
            return RobotsRules.allow_all()
        if page.status_code not in (200, 204):
            return RobotsRules.allow_all()
        return RobotsRules.parse(page.body, user_agent=self._client.user_agent)


def build_scan_service(client: ScanHTTPClient | None = None) -> ScanService:
    """Instantiate the scanner from settings (``SCAN_*`` env vars).

    ``client`` lets the caller reuse one session jar per run (the Carro's M2
    re-probes authenticate with the same session the scan established).
    """
    from app.core.config import get_settings

    settings = get_settings()
    if client is None:
        client = ScanHTTPClient(
            rate_limit=settings.scan_rate_limit,
            timeout=settings.scan_request_timeout,
            max_body_bytes=settings.scan_max_body_bytes,
            user_agent=settings.scan_user_agent,
            extra_headers=settings.scan_extra_headers,
            cookies=settings.scan_cookies,
        )
    return ScanService(
        client=client,
        respect_robots=settings.scan_respect_robots,
        max_pages=settings.scan_max_pages,
        depth=settings.scan_depth or None,
        login_url=settings.scan_login_url,
        login_username=settings.scan_login_username,
        login_password=settings.scan_login_password,
    )