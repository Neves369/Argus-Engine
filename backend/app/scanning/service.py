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

<<<<<<< HEAD
    async def scan(
        self, target: dict[str, Any], *, max_pages: int | None = None
    ) -> ScanReport:
=======
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

    async def scan(self, target: dict[str, Any]) -> ScanReport:
>>>>>>> b73867b (feat(scan,report,tools): refinar relatório do scan (M1) e re-provar leads pelo Carro (M2))
        target_name = str((target or {}).get("name") or "")
        try:
            validate_scope(target_name)
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
        for base_url in candidates:
            attempt = await self._crawl(base_url, max_pages=max_pages)
            report.pages = attempt.pages
            report.urls_skipped_by_robots += attempt.urls_skipped_by_robots
            if attempt.robots_respected is not None:
                report.robots_respected = attempt.robots_respected
            if attempt.pages:
                report.note = attempt.note
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

    async def _crawl(self, base_url: str, *, max_pages: int | None = None) -> ScanReport:
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


<<<<<<< HEAD
def build_scan_service() -> ScanService:
    """Instantiate the scanner from settings (``SCAN_*`` env vars)."""
=======
def _select_login_form(forms: list[HtmlForm]) -> HtmlForm | None:
    """Pick the first form with a password field (the login form candidate)."""
    for form in forms:
        if any(fld.type == "password" for fld in form.fields):
            return form
    return None


def _login_payload(form: HtmlForm, username: str, password: str) -> dict[str, str]:
    """Map the login form fields to submitted values, deterministically.

    The username goes into the first unfilled text-like field (so prefilled or
    CSRF-bearing text inputs are left alone); hidden fields keep their value.
    """
    data: dict[str, str] = {}
    text_fields: list[FormField] = []
    for fld in form.fields:
        if not fld.name:
            continue
        if fld.type == "password":
            data[fld.name] = password
        elif fld.type == "hidden":
            if fld.value:
                data[fld.name] = fld.value
        elif fld.type in ("text", "email", "username", "tel", "search"):
            if fld.value:
                data[fld.name] = fld.value
            else:
                text_fields.append(fld)
    username_field = text_fields[0] if text_fields else None
    if username_field is not None:
        data[username_field.name] = username
    return data


def build_scan_service(client: ScanHTTPClient | None = None) -> ScanService:
    """Instantiate the scanner from settings (``SCAN_*`` env vars).

    ``client`` lets the caller reuse one session jar per run (the Carro's M2
    re-probes authenticate with the same session the scan established).
    """
>>>>>>> b73867b (feat(scan,report,tools): refinar relatório do scan (M1) e re-provar leads pelo Carro (M2))
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