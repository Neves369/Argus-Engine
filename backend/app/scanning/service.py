from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

import yaml

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
    #: OpenAPI/Swagger observado (M8-P0): {url, sha256, session} ou None.
    api_spec: dict[str, Any] | None = None
    #: Endpoints mapeados do spec: {method, path, params, session}.
    api_endpoints: list[dict[str, Any]] = field(default_factory=list)
    #: Endpoints GraphQL detectados passivamente (M8-P2):
    #: {url, session, detected_by} — lead para o probe de introspecção.
    graphql_endpoints: list[dict[str, Any]] = field(default_factory=list)

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
            "api_spec": self.api_spec,
            "api_endpoints": list(self.api_endpoints),
            "graphql_endpoints": list(self.graphql_endpoints),
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
        session_profiles: list[dict[str, str]] | None = None,
        client_factory: Any | None = None,
        openapi_enabled: bool = False,
        openapi_discovery_paths: list[str] | None = None,
        graphql_enabled: bool = False,
        graphql_discovery_paths: list[str] | None = None,
    ) -> None:
        self._client = client or ScanHTTPClient()
        self._respect_robots = respect_robots
        self._max_pages = max(1, int(max_pages))
        self._depth = self._resolve_depth(depth)
        self._login_url = login_url
        self._login_username = login_username
        self._login_password = login_password
        self._session_profiles = []
        for profile in (session_profiles or []):
            normalized = self._normalize_profile(profile)
            if normalized is not None:
                self._session_profiles.append(normalized)
        self._client_factory = client_factory
        self._active_channels: list[dict[str, Any]] | None = None
        self._openapi_enabled = bool(openapi_enabled)
        self._openapi_paths = [
            f"/{str(p).strip().lstrip('/')}"
            for p in (openapi_discovery_paths or [])
            if str(p).strip()
        ] or ["/openapi.json", "/swagger.json", "/openapi.yaml"]
        self._graphql_enabled = bool(graphql_enabled)
        self._graphql_paths = [
            f"/{str(p).strip().lstrip('/')}"
            for p in (graphql_discovery_paths or [])
            if str(p).strip()
        ] or ["/graphql", "/graphql/", "/gql", "/api/graphql"]

    def _normalize_profile(self, profile: dict[str, str]) -> dict[str, str] | None:
        """Validate a session profile dict; ``None`` when unusable (skipped)."""
        login_url = str(profile.get("login_url") or "").strip()
        username = str(profile.get("username") or "").strip()
        password = str(profile.get("password") or "")
        name = str(profile.get("name") or "").strip()
        if not (login_url and username and password):
            logger.warning(
                "scan session profile incompleto (ignorado)",
                extra={"profile": name or "<sem nome>", "reason": "login_url/username/password"},
            )
            return None
        return {
            "name": name or "perfil",
            "login_url": login_url,
            "username": username,
            "password": password,
        }

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
        channels = self._channel_profiles()
        override = self._max_pages if max_pages is None else max(1, int(max_pages))
        if channels:
            return await self._scan_multi(report, channels, candidates, override, derived)

        await self._authenticate(report)
        session = "user" if report.auth_status == "success" else "anon"
        if session == "user":
            self._active_channels = [{"name": "user", "client": self._client}]
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
                await self._discover_openapi(
                    report, base_url, client=self._client, session=session
                )
                await self._discover_graphql(
                    report, base_url, client=self._client, session=session
                )
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

    async def _scan_multi(
        self,
        report: ScanReport,
        channels: list[dict[str, Any]],
        candidates: list[str],
        override: int,
        derived: bool,
    ) -> ScanReport:
        """M7-P1: crawl per session profile with isolated clients.

        The base candidate is resolved by the primary profile's crawl (shared
        client), then every other profile crawls the same base with its own
        jar. Pages are labeled per profile; ``report.auth*`` stay the primary's
        legacy fields, while every channel lands in ``report.sessions``.
        """
        self._active_channels = channels
        profiles = channels[0]
        await self._authenticate(
            report,
            client=profiles["client"],
            login_url=profiles["login_url"],
            login_username=profiles["username"],
            login_password=profiles["password"],
        )
        extras = [
            await self._authenticate_profile(profile) for profile in channels[1:]
        ]

        selected_base: str | None = None
        for base_url in candidates:
            attempt = await self._crawl(
                base_url,
                max_pages=override,
                session=profiles["name"],
                client=profiles["client"],
            )
            report.pages = attempt.pages
            report.urls_skipped_by_robots += attempt.urls_skipped_by_robots
            if attempt.robots_respected is not None:
                report.robots_respected = attempt.robots_respected
            if attempt.pages:
                report.note = attempt.note
                selected_base = base_url
                break
            if not derived and attempt.note:
                report.note = attempt.note
                break

        if selected_base is None:
            report.note = (
                "Nenhuma página acessível retornou conteúdo dentro dos "
                "controles de escopo."
            )
            self._finalize_multi_sessions(report, channels, extras)
            return report

        for profile in channels[1:]:
            attempt = await self._crawl(
                selected_base,
                max_pages=override,
                session=profile["name"],
                client=profile["client"],
            )
            report.pages.extend(attempt.pages)
            report.urls_skipped_by_robots += attempt.urls_skipped_by_robots
            if attempt.robots_respected is not None:
                report.robots_respected = attempt.robots_respected

        if any(
            rec["auth_status"] == "success"
            for rec in [{"auth_status": report.auth_status}, *extras]
        ):
            report.anon_probe = await self._anonymous_baseline([selected_base])
        await self._discover_openapi(
            report, selected_base, client=profiles["client"], session=profiles["name"]
        )
        await self._discover_graphql(
            report, selected_base, client=profiles["client"], session=profiles["name"]
        )
        self._finalize_multi_sessions(report, channels, extras)
        return report

    async def _discover_openapi(
        self,
        report: ScanReport,
        base_url: str,
        *,
        client: ScanHTTPClient,
        session: str,
    ) -> None:
        """M8-P0: tenta obter a spec OpenAPI/Swagger oficial da base.

        Roda com o client/jar da sessão que crawleou a base (a spec pode ser
        autenticada), respeitando robots por path, rate-limit, timeout e o teto
        de bytes do client. Fail-closed: spec inválida, sem ``paths`` válidos
        ou servers fora do host → nota no relatório, sem superfície.
        """
        if not self._openapi_enabled or not base_url:
            return
        robots = (
            await self._load_robots(base_url)
            if self._respect_robots
            else RobotsRules.allow_all()
        )
        host = urlparse(base_url).netloc
        for rel in self._openapi_paths:
            url = urljoin(base_url, rel.lstrip("/"))
            if not robots.is_allowed(urlparse(url).path or "/"):
                report.urls_skipped_by_robots += 1
                continue
            try:
                page = await client.get_page(url)
            except ScanError as exc:
                report.note = self._note_append(
                    report.note, f"spec {rel}: indisponível ({exc})"
                )
                continue
            if page.status_code not in (200, 204):
                continue
            spec = self._parse_openapi(page.body)
            if spec is None:
                report.note = self._note_append(
                    report.note, f"spec {rel}: inválida (sem paths válidos)"
                )
                continue
            report.api_spec = {
                "url": url,
                "sha256": hashlib.sha256(page.body.encode("utf-8")).hexdigest(),
                "session": session,
            }
            report.api_endpoints = [
                {
                    "method": method.upper(),
                    "path": path,
                    "params": params,
                    "session": session,
                    "url": urljoin(base_url, path),
                }
                for path, methods in spec.items()
                if urlparse(urljoin(base_url, path)).netloc == host
                for method, params in methods.items()
            ]
            return

    @staticmethod
    def _parse_openapi(body: str) -> dict[str, dict[str, list[str]]] | None:
        """Extrai {path: {método: [parâmetros]}} da spec; None se inválida."""
        try:
            data = yaml.safe_load(body)
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        paths = data.get("paths")
        if not isinstance(paths, dict) or not paths:
            return None
        spec: dict[str, dict[str, list[str]]] = {}
        for path, item in paths.items():
            if not isinstance(item, dict):
                continue
            methods: dict[str, list[str]] = {}
            for method in ("get", "post", "put", "patch", "delete", "head", "options"):
                op = item.get(method)
                if not isinstance(op, dict):
                    continue
                params = [
                    str(p.get("name") or "")
                    for p in op.get("parameters") or []
                    if isinstance(p, dict) and p.get("name")
                ]
                methods[method] = params
            if methods:
                spec[str(path)] = methods
        return spec or None

    @staticmethod
    def _note_append(note: str | None, extra: str) -> str | None:
        return f"{note}\n{extra}" if note else extra

    async def _discover_graphql(
        self,
        report: ScanReport,
        base_url: str,
        *,
        client: ScanHTTPClient,
        session: str,
    ) -> None:
        """M8-P2: detecta endpoints GraphQL por caminhos canônicos + referências.

        Detecção passiva de superfície — nenhuma introspecção aqui (isso é um
        probe sob política). Tenta cada caminho canônico via GET (mesmos
        guardrails do client: rate-limit, timeout, teto de bytes, robots) e
        varre o HTML/JS das páginas crawleadas por referências a ``graphql``.
        Fail-closed: nada casa → nota no relatório, sem superfície.
        """
        if not self._graphql_enabled or not base_url:
            return
        robots = (
            await self._load_robots(base_url)
            if self._respect_robots
            else RobotsRules.allow_all()
        )
        host = urlparse(base_url).netloc
        endpoints: list[dict[str, Any]] = []
        seen: set[str] = set()

        for rel in self._graphql_paths:
            url = urljoin(base_url, rel.lstrip("/"))
            if urlparse(url).netloc != host:
                continue
            if not robots.is_allowed(urlparse(url).path or "/"):
                report.urls_skipped_by_robots += 1
                continue
            try:
                page = await client.get_page(url)
            except ScanError as exc:
                report.note = self._note_append(
                    report.note, f"graphql {rel}: indisponível ({exc})"
                )
                continue
            if not self._looks_like_graphql(page.status_code, page.body):
                continue
            if url not in seen:
                seen.add(url)
                endpoints.append(
                    {"url": url, "method": "POST", "session": session, "detected_by": "path"}
                )

        for page in report.pages:
            for ref in self._graphql_references(page.body):
                resolved = urljoin(page.url, ref)
                if urlparse(resolved).netloc != host:
                    continue
                if resolved not in seen:
                    seen.add(resolved)
                    endpoints.append(
                        {
                            "url": resolved,
                            "method": "POST",
                            "session": page.session,
                            "detected_by": "reference",
                        }
                    )

        if not endpoints:
            report.note = self._note_append(
                report.note, "graphql: nenhum endpoint detectado"
            )
            return
        report.graphql_endpoints = endpoints

    @staticmethod
    def _looks_like_graphql(status_code: int, body: str) -> bool:
        """Heurística conservadora de que uma resposta é um endpoint GraphQL.

        Só casa com marcadores explícitos (nunca "parece GraphQL" por acaso):
        erros de falta de query, ou conteúdo JSON com ``errors`` típico de um
        GraphQL server rejeitando GET sem query.
        """
        lowered = body.lower()
        markers = (
            "must provide query string",
            "query missing",
            "get query missing",
            "graphql query",
        )
        if any(m in lowered for m in markers):
            return True
        if "graphql" not in lowered:
            return False
        return status_code in (400, 405) and ("query" in lowered or "errors" in lowered)

    @staticmethod
    def _graphql_references(body: str) -> list[str]:
        """URLs do próprio host referenciadas como GraphQL no HTML/JS.

        Varre atributos/strings como ``/graphql``, ``graphql?query=`` em tags
        e scripts — apenas observação, sem execução.
        """
        matches: list[str] = []
        for m in re.findall(r"""[-\w./]*graphql[-\w./?#&=]*""", body, re.IGNORECASE):
            candidate = m.strip()
            if not candidate or candidate.lower() == "graphql":
                continue
            if any(token in candidate.lower() for token in (".js", ".css", ".png", ".svg")):
                continue
            matches.append(candidate)
        return matches

    def _finalize_multi_sessions(
        self,
        report: ScanReport,
        channels: list[dict[str, Any]],
        extras: list[dict[str, Any]],
    ) -> None:
        """Build ``report.sessions`` from the per-profile crawl (M7-P1)."""
        session_counts: dict[str, int] = {}
        for page in report.pages:
            session_counts[page.session] = session_counts.get(page.session, 0) + 1
        report.sessions = [
            {
                "name": profiles["name"],
                "auth_status": (
                    report.auth_status
                    if index == 0
                    else (extras[index - 1] or {}).get("auth_status")
                ),
                "auth": report.auth if index == 0 else (extras[index - 1] or {}).get("auth"),
                "auth_cookies": (
                    list(report.auth_cookies)
                    if index == 0
                    else list((extras[index - 1] or {}).get("auth_cookies", []))
                ),
                "page_count": session_counts.get(profiles["name"], 0),
            }
            for index, profiles in enumerate(channels)
        ]

    def _base_candidates(self, target: dict[str, Any]) -> list[str]:
        """Candidate base URLs: explicit url first, else https then http."""
        name = str(target.get("name") or "").strip()
        url = str(target.get("url") or "").strip()
        if url:
            if not url.startswith(("http://", "https://")):
                url = f"http://{url}"
            return [url.rstrip("/") + "/"]
        return [f"https://{name}/", f"http://{name}/"]

    async def _authenticate(
        self,
        report: ScanReport,
        *,
        client: ScanHTTPClient | None = None,
        login_url: str | None = None,
        login_username: str | None = None,
        login_password: str | None = None,
    ) -> None:
        """Submit the target's login form once and reuse the session cookies.

        Fills ``report.auth`` (note), ``report.auth_status``
        (``skipped|attempted|success|failed``) and ``report.auth_cookies``
        (cookie *names* only — never values, so the report stays auditable and
        redacted). A failed/partial login does NOT block the scan — the crawl
        proceeds unauthenticated and the outcome is recorded/auditable.

        ``client``/``login_*`` override the instance defaults (M7-P1): each
        session profile authenticates on its own isolated client.
        """
        client = client or self._client
        login_url = self._login_url if login_url is None else login_url
        login_username = (
            self._login_username if login_username is None else login_username
        )
        login_password = (
            self._login_password if login_password is None else login_password
        )
        if not (login_url and login_username and login_password):
            report.auth_status = "skipped"
            return
        report.auth_status = "attempted"
        try:
            page = await client.get_page(login_url)
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
        data = login_payload(form, login_username, login_password)
        try:
            if form.method == "post":
                response = await client.post_page(action, data)
            else:
                joined = urljoin(action, "?" + urlencode(data))
                response = await client.get_page(joined)
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
        report.auth_cookies = client.session_cookie_names(urlparse(login_url).netloc)

    async def _authenticate_profile(self, profile: dict[str, str]) -> dict[str, Any]:
        """Authenticate one session profile; returns its session metadata.

        Does not touch the report — used for the additional profiles in M7-P1.
        """
        probe_report = ScanReport(target="session-profile")
        await self._authenticate(
            probe_report,
            client=profile["client"],
            login_url=profile["login_url"],
            login_username=profile["username"],
            login_password=profile["password"],
        )
        return {
            "name": profile["name"],
            "auth_status": probe_report.auth_status,
            "auth": probe_report.auth,
            "auth_cookies": list(probe_report.auth_cookies),
        }

    def _channel_profiles(self) -> list[dict[str, Any]] | None:
        """Session channels for a run: ``None`` when only the single login.

        Profiles from config (M7-P1) replace the single ``SCAN_LOGIN_*`` login.
        The first profile reuses the run's shared client (so the verifier and
        the M6 probe engine keep the primary session); every extra profile runs
        on a fresh isolated client (its own cookie jar).
        """
        if not self._session_profiles:
            return None
        channels: list[dict[str, Any]] = []
        for index, profile in enumerate(self._session_profiles):
            channels.append(
                {
                    "name": profile["name"],
                    "client": self._client if index == 0 else self._new_client(),
                    "login_url": profile["login_url"],
                    "username": profile["username"],
                    "password": profile["password"],
                }
            )
        return channels

    def session_clients(self) -> dict[str, Any]:
        """Clients dos perfis autenticados no último scan (M7-P2).

        Mantém vivas as jars por perfil para que o ProbeEngine reprove os leads
        com o client da sessão observada — primário (shared) quando single
        profile, e o jar isolado de cada perfil extra. Nunca serializado: os
        clients (e seus cookies) ficam apenas em memória no escopo do run.
        """
        return {
            channel["name"]: channel["client"]
            for channel in (self._active_channels or [])
            if channel.get("name") and channel.get("client") is not None
        }

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
        """A fresh anonymous client (empty session jar) for baseline/profiles.

        Uses the injected ``client_factory`` when provided (tests share the
        run's rate-limiting semantics), else mirrors the settings.
        """
        if self._client_factory is not None:
            client = self._client_factory()
            if client is not None:
                return client
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
        self,
        base_url: str,
        *,
        max_pages: int | None = None,
        session: str = "anon",
        client: ScanHTTPClient | None = None,
    ) -> ScanReport:
        """BFS crawl of same-host pages bounded by ``max_pages`` (or the
        instance default when omitted — ``deep`` runs may override per call).

        ``client`` lets M7-P1 crawl each session profile with its own isolated
        jar; default is the run's shared client.
        """
        client = client or self._client
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
                page = await client.get_page(url)
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
        session_profiles=settings.scan_session_profiles,
        openapi_enabled=settings.scan_openapi_enabled,
        openapi_discovery_paths=settings.scan_openapi_discovery_paths,
        graphql_enabled=settings.scan_graphql_enabled,
        graphql_discovery_paths=settings.scan_graphql_paths,
    )