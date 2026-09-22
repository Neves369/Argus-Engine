"""Jornadas multi-step (Etapa M7-P3): login → ação → efeito observado por papel.

Diferente das políticas de probe (M6, que reprovam um *lead observado*), uma
jornada é um fluxo que o operador escreve e versiona em
``policies/journeys/*.yaml`` (ex.: "abrir o painel", "criar um registro",
"consultar um recurso") — uma sequência de passos (requisição literal +
efeito esperado) que o Argus re-executa **idêntica** para anônimo e para cada
sessão autenticada do run.

Princípios (ver ROADMAP_ARGUS_PODEROSO.md, M7):
- o Argus **não inventa** passo: ``path``/``body``/``expect`` vêm do catálogo
  versionado; ``body`` é literal e estático (nunca credenciais reais);
- toda requisição passa por kill-switch + ``ALLOWED_SCOPES`` + robots +
  rate-limit do ``ScanHTTPClient`` compartilhado do run;
- cada passo gera registro auditável (request/response resumidos + sessão);
- o resultado é comparado entre as sessões: quando o mesmo passo alcança o
  efeito esperado em um papel e não em outro, nasce um finding candidate de
  comportamento (controle de acesso observado, sem enumeração agressiva).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from app.core.security import is_kill_switch_active, validate_scope
from app.journeys.catalog import journey_digest, load_catalog
from app.journeys.schemas import Journey, JourneyStep
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.robots import RobotsRules

logger = logging.getLogger(__name__)

JOURNEY_CATEGORY_PREFIX = "Comportamento / Jornada / "
_MISSING = object()


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _host(url: str) -> str:
    return urlparse(url).netloc


class JourneyEngine:
    """Executa as jornadas do catálogo dentro dos guardrails do run."""

    def __init__(
        self,
        *,
        client: ScanHTTPClient | None = None,
        enabled: bool = True,
        max_steps_per_session: int = 20,
        respect_robots: bool = True,
        default_classes: str = "p0",
        catalog: dict[str, Journey] | None = None,
    ) -> None:
        self._client = client or ScanHTTPClient()
        self._enabled = bool(enabled)
        self._max_steps = max(1, int(max_steps_per_session or 1))
        self._respect_robots = bool(respect_robots)
        self._default = default_classes or "p0"
        self._catalog = catalog if catalog is not None else load_catalog()
        self._robots_cache: dict[str, RobotsRules | None] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled and bool(self._catalog)

    def active_journeys(self, requested: list[str] | None) -> list[str]:
        """Ids efetivos: pedido explícito (somente ids existentes) ou allowlist."""
        if requested:
            return [jid for jid in requested if jid in self._catalog]
        return self._classes()

    def _classes(self) -> list[str]:
        order = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
        allow = order.get(self._default.strip().lower(), 0)
        return sorted(
            jid
            for jid, journey in self._catalog.items()
            if order.get(journey.priority.lower(), 99) <= allow
            and journey.default_enabled
        )

    async def run(
        self,
        *,
        target: dict[str, Any] | None,
        session_clients: dict[str, ScanHTTPClient] | None = None,
        journey_ids: list[str] | None = None,
        anon_client: ScanHTTPClient | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa as jornadas habilitadas; retorna (findings, registros).

        Determininístico e fail-closed: sem escopo válido, kill-switch ativo,
        catálogo vazio ou sem alvo, nada roda e devolve vazios.
        """
        if not self.enabled or not target:
            return [], []
        try:
            validate_scope(str(target.get("name") or "unknown"))
        except ValueError:
            return [], []
        if is_kill_switch_active():
            return [], []

        ids = self.active_journeys(journey_ids)
        if not ids:
            return [], []

        base = self._base_url(target)
        if not _host(base):
            return [], []

        connected = sorted((session_clients or {}).items())

        behavior_findings: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        for jid in ids:
            journey = self._catalog[jid]
            channels: list[tuple[str, ScanHTTPClient]] = []
            if journey.run_anonymous:
                channels.append(("anon", anon_client or self._client))
            channels.extend(connected)
            data, journey_records = await self._run_journey(
                journey, base, channels, executed=len(records)
            )
            records.extend(journey_records)
            finding = self._divergence_finding(journey, data)
            if finding is not None:
                behavior_findings.append(finding)
        return behavior_findings, records

    def _base_url(self, target: dict[str, Any]) -> str:
        name = str(target.get("name") or "").strip()
        url = str(target.get("url") or "").strip()
        if url:
            if not url.startswith(("http://", "https://")):
                url = f"http://{url}"
            return url.rstrip("/") + "/"
        return f"https://{name}/"

    async def _run_journey(
        self,
        journey: Journey,
        base: str,
        channels: list[tuple[str, ScanHTTPClient]],
        executed: int,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Roda a jornada por canal; retorna (outcomes por passo, registros)."""
        host = _host(base)
        data: dict[str, dict[str, dict[str, Any]]] = {}
        records: list[dict[str, Any]] = []
        for session, client in channels:
            for index, step in enumerate(journey.steps):
                if executed >= self._max_steps:
                    records.append(
                        self._record(
                            journey, step, session, index,
                            url=urljoin(base, step.path.lstrip("/") or "/"),
                            skipped=True, skip_reason="max steps cap",
                        )
                    )
                    continue
                url = urljoin(base, step.path.lstrip("/") or "/")
                if _host(url) != host:
                    records.append(
                        self._record(
                            journey, step, session, index, url=url,
                            skipped=True, skip_reason=f"fora do host ({_host(url)})",
                        )
                    )
                    continue
                blocked = await self._robots_blocked(host, url)
                if blocked is not None:
                    records.append(
                        self._record(
                            journey, step, session, index, url=url,
                            skipped=True, skip_reason=blocked,
                        )
                    )
                    continue
                try:
                    if step.method == "POST":
                        page = await client.post_page(url, step.body)
                    else:
                        page = await client.get_page(url)
                except ScanError as exc:  # noqa: BLE001 - transcrito como registro
                    record = self._record(
                        journey, step, session, index, url=url,
                        skipped=True, skip_reason=f"unreachable: {exc}",
                    )
                else:
                    ok = self._step_ok(step, page)
                    record = self._record(
                        journey, step, session, index, url=url,
                        status_code=page.status_code,
                        final_url=page.url,
                        effect_ok=ok,
                        detail=(
                            f"efeito {'alcançado' if ok else 'não alcançado'} "
                            f"[HTTP {page.status_code}]"
                        ),
                    )
                data.setdefault(index, {}).setdefault(session, record)
                records.append(record)
                executed += 1
        return data, records

    @staticmethod
    def _step_ok(step: JourneyStep, page: Any) -> bool:
        if page.status_code not in step.expect.status_in:
            return False
        if step.expect.contains:
            return step.expect.contains.lower() in page.body.lower()
        return True

    def _divergence_finding(
        self, journey: Journey, data: dict[str, dict[str, dict[str, Any]]]
    ) -> dict[str, Any] | None:
        """Um finding quando algum passo alcança efeito diferente entre papéis."""
        divergent: list[dict[str, Any]] = []
        lines: list[str] = []
        sessions_seen: set[str] = set()
        for index in sorted(data):
            step_ok: dict[str, bool] = {}
            for session, record in data[index].items():
                sessions_seen.add(session)
                if record.get("skipped"):
                    continue
                step_ok[session] = bool(record.get("effect_ok"))
            if len(set(step_ok.values())) < 2:
                continue
            ok_sessions = sorted(s for s, ok in step_ok.items() if ok)
            not_ok_sessions = sorted(s for s, ok in step_ok.items() if not ok)
            step = journey.steps[index]
            divergent.append(
                {
                    "step": step.name,
                    "path": step.path,
                    "method": step.method,
                    "sessions_cs": ok_sessions,
                    "sessions_failed": not_ok_sessions,
                }
            )
            lines.append(
                f"- {step.name} ({step.method} {step.path}): alcançado em "
                f"{', '.join(ok_sessions) or 'nenhuma'}; não alcançado em "
                f"{', '.join(not_ok_sessions) or 'nenhuma'}"
            )
        if not divergent:
            return None
        title = journey.reporting.title_template.format(name=journey.name)
        return {
            "id": None,
            "title": title,
            "description": journey.description,
            "severity": journey.candidate_severity,
            "category": f"{JOURNEY_CATEGORY_PREFIX}{journey.name}",
            "affected": "unknown",
            "cvss_score": None,
            "cvss_vector": None,
            "cves": [],
            "known_exploits": [],
            "remediation": journey.reporting.remediation,
            "references": journey.reporting.references or ["https://owasp.org/Top10/"],
            "evidence": (
                f"A jornada '{journey.name}' teve efeito dependente de sessão:\n"
                + "\n".join(lines)
            ),
            "confidence": journey.reporting.confidence,
            "status": "candidate",
            "requires_human_review": journey.requires_hitl,
            "extras": {
                "journey": {
                    "id": journey.id,
                    "name": journey.name,
                    "version": journey.version,
                    "sha256": journey_digest(journey),
                },
                "divergent_steps": divergent,
                "sessions": sorted(sessions_seen),
            },
        }

    def _record(
        self,
        journey: Journey,
        step: JourneyStep,
        session: str,
        index: int,
        *,
        url: str,
        final_url: str | None = None,
        status_code: int | None = None,
        effect_ok: bool = False,
        skipped: bool = False,
        skip_reason: str | None = None,
        detail: str = "",
    ) -> dict[str, Any]:
        return {
            "journey_id": journey.id,
            "journey_version": journey.version,
            "journey_sha256": journey_digest(journey),
            "journey_name": journey.name,
            "step": step.name,
            "step_index": index,
            "session": session,
            "method": step.method,
            "url": url,
            "final_url": final_url,
            "host": _host(url),
            "status_code": status_code,
            "effect_ok": bool(effect_ok),
            "skipped": bool(skipped),
            "skip_reason": skip_reason,
            "detail": detail,
            "observed_at": _utcnow(),
        }

    # ------------------------------------------------------------------
    # Controles compartilhados com o scanning/probing ativos
    # ------------------------------------------------------------------
    async def _robots_blocked(self, host: str, url: str) -> str | None:
        if not self._respect_robots:
            return None
        rules = self._robots_cache.get(host, _MISSING)
        if rules is _MISSING:
            rules = await self._load_robots(host)
            self._robots_cache[host] = rules
        if rules is None:
            return None
        if rules.is_allowed(urlparse(url).path or "/"):
            return None
        return "robots disallow"

    async def _load_robots(self, host: str) -> RobotsRules | None:
        robots_url = urljoin(f"https://{host}/", "robots.txt")
        try:
            page = await self._client.fetch_no_rate_limit(robots_url)
        except ScanError:
            return None
        if page.status_code not in (200, 204):
            return None
        return RobotsRules.parse(page.body, user_agent=self._client.user_agent)


def build_journey_engine(client: ScanHTTPClient | None = None) -> JourneyEngine:
    """Instancia o motor a partir das settings (``JOURNEY_*``) e do catálogo."""
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
    return JourneyEngine(
        client=client,
        enabled=settings.journey_enabled,
        max_steps_per_session=settings.journey_max_steps_per_session,
        respect_robots=settings.journey_respect_robots,
        default_classes=settings.journey_classes_default,
    )