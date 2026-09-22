"""Motor de probes de comportamento sob política (Etapa M6).

Diferente do re-probe do Carro (M2, que só reconfirma o lead que o crawl já
observou), aqui o Argus aplica **políticas versionadas** (`policies/probes/*.yaml`)
para transformar um lead observacional em um sinal de comportamento
*reproduzível* — sempre com ações mínimas, no escopo, com
rate-limit/robots/teto de probes, e evidência estruturada por regra.

Princípios de projeto (ver ROADMAP_ARGUS_PODEROSO.md, M6):

- o LLM **não** inventa probe: ele não participa — só o catálogo aprovado roda;
- nenhuma política envia payload/exploit; os valores usados são apenas os que o
  crawl já observou (ou nenhum, em observação pura de forms/redirect); authn
  (P3) envia um diferencial mínimo de login com controles sentinela — nunca
  credenciais reais, nunca brute force;
- toda ação passa por kill-switch + ``ALLOWED_SCOPES`` + robots + rate-limit do
  ``ScanHTTPClient`` compartilhado do run;
- cada probe gera um registro auditável (request/response resumidos + regra).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urljoin, urlparse

from app.core.security import is_kill_switch_active, validate_scope
from app.probing.catalog import catalog_digest, load_catalog
from app.probing.schemas import ProbePolicy, SignalRule
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.detectors import _VERBOSE_ERROR_MARKERS
from app.scanning.login import login_payload, select_login_form
from app.scanning.parsers import parse_html
from app.scanning.robots import RobotsRules
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage

logger = logging.getLogger(__name__)

BEHAVIOR_CATEGORY_PREFIX = "Comportamento / "

_PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
_TOKEN_NAME_HINTS = ("csrf", "token", "_token", "authenticity", "anticsrf")
_BROAD_ACCEPT = ("", "*/*", "image/*", "*")
_EDITABLE_TYPES = ("text", "email", "search", "url", "number", "tel")
_PASSWORD_HINTS = ("pass", "senha", "pwd", "secret", "chave")
#: Controles sentinela do diferencial P3 (authn): nunca credenciais reais, e
#: nunca um brute force — dois envios com a MESMA senha sentinela e usuários
#: distintos revelam se a aplicação discrimina a existência de conta.
_AUTHN_SENTINEL_PASSWORD = "argus-control-password"
_AUTHN_DIFFERENTIAL_USERS = ("admin", "argus_nonexistent_user")


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _host(url: str) -> str:
    return urlparse(url).netloc


@dataclass
class _Lead:
    """Endpoint observado que ativa uma política (nunca um alvo inventado)."""

    url: str
    detail: str
    param: str | None = None
    value: str | None = None
    method: str = "GET"
    fields: list[str] = field(default_factory=list)
    differential: bool | None = None
    session: str = "anon"


class ProbeEngine:
    """Aplica as políticas do catálogo M6 dentro dos guardrails do run."""

    def __init__(
        self,
        *,
        client: ScanHTTPClient | None = None,
        enabled: bool = True,
        max_probes: int = 10,
        max_per_endpoint: int = 2,
        respect_robots: bool = True,
        default_classes: str = "p0",
        catalog: dict[str, ProbePolicy] | None = None,
        session_clients: dict[str, ScanHTTPClient] | None = None,
    ) -> None:
        self._client = client or ScanHTTPClient()
        self._session_clients = session_clients or {}
        self._enabled = bool(enabled)
        self._max_probes = max(0, int(max_probes or 0))
        self._max_per_endpoint = max(1, int(max_per_endpoint or 1))
        self._respect_robots = bool(respect_robots)
        self._default = default_classes or "p0"
        self._catalog = catalog if catalog is not None else load_catalog()
        self._robots_cache: dict[str, RobotsRules | None] = {}

    @property
    def enabled(self) -> bool:
        return self._enabled and self._max_probes > 0

    def resolve_classes(self, requested: list[str] | None) -> list[str]:
        """Allowlist efetiva de classes: pedido explícito ou default por prioridade.

        Um pedido explícito só é honrado para ids existentes no catálogo — o
        operador nunca libera uma classe que não esteja aprovada/versionada.
        """
        if requested:
            return [cid for cid in requested if cid in self._catalog]
        return sorted(
            pid
            for pid, policy in self._catalog.items()
            if _PRIORITY_ORDER.get(policy.priority.lower(), 99)
            <= _PRIORITY_ORDER.get(self._default.strip().lower(), 0)
            and policy.default_enabled
        )

    async def run(
        self,
        *,
        report: ScanReport | None,
        findings: list[dict[str, Any]],
        target: dict[str, Any] | None = None,
        probe_classes: list[str] | None = None,
        session_clients: dict[str, ScanHTTPClient] | None = None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Executa as políticas liberadas; retorna (findings, registros de probe).

        Determinístico e fail-closed: sem escopo válido, kill-switch ativo, sem
        páginas observadas ou sem classe liberada, nada roda e devolve vazios.
        """
        if not self.enabled or report is None or not report.pages:
            return [], []
        target_name = str((target or {}).get("name") or "")
        try:
            validate_scope(target_name)
        except ValueError:
            return [], []
        if is_kill_switch_active():
            return [], []

        classes = self.resolve_classes(probe_classes)
        if not classes:
            return [], []

        self._session_clients = session_clients or {}

        behavior_findings: list[dict[str, Any]] = []
        records: list[dict[str, Any]] = []
        executed = 0
        per_endpoint: dict[str, int] = {}

        for class_id in classes:
            policy = self._catalog.get(class_id)
            if policy is None:
                continue
            positive: list[dict[str, Any]] = []
            for lead in self._collect_leads(policy, report, findings):
                if executed >= self._max_probes:
                    break
                if per_endpoint.get(lead.url, 0) >= self._max_per_endpoint:
                    records.append(
                        self._record(policy, lead, skipped=True, skip_reason="per-endpoint cap")
                    )
                    continue
                record = await self._probe(policy, lead)
                per_endpoint[lead.url] = per_endpoint.get(lead.url, 0) + 1
                if not record.get("skipped"):
                    executed += 1
                records.append(record)
                if record.get("positive"):
                    positive.append(record)
            if positive:
                behavior_findings.append(self._behavior_finding(policy, positive))

        return behavior_findings, records

    # ------------------------------------------------------------------
    # Coleta de leads (evidence-grounded: só o que o crawl/scan observou)
    # ------------------------------------------------------------------
    def _collect_leads(
        self, policy: ProbePolicy, report: ScanReport, findings: list[dict[str, Any]]
    ) -> list[_Lead]:
        lead_kind = policy.precondition.lead
        leads: list[_Lead] = []
        seen: set[str] = set()

        def _add(lead: _Lead) -> None:
            key = f"{lead.url}|{lead.param or ''}|{lead.session}"
            if lead.url and key not in seen:
                seen.add(key)
                leads.append(lead)

        if lead_kind == "reflection":
            for finding in self._findings_matching(policy, findings, "Aplicação / reflexão"):
                for ref in (finding.get("extras") or {}).get("reflections") or []:
                    url = str(ref.get("probe_url") or ref.get("url") or "").strip()
                    if not url:
                        continue
                    _add(
                        _Lead(
                            url=url,
                            detail=f"param {ref.get('param')} observado refletido",
                            param=str(ref.get("param") or "") or None,
                            value=str(ref.get("value") or ""),
                            session=str(ref.get("session") or "anon"),
                        )
                    )
        elif lead_kind == "verbose_error":
            for finding in self._findings_matching(policy, findings, None):
                url = str(finding.get("probe_url") or finding.get("affected") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                sessions = finding.get("sessions") or [finding.get("session") or "anon"]
                for session in sessions:
                    _add(
                        _Lead(
                            url=url,
                            detail="erro verboso observado no crawl",
                            session=str(session or "anon"),
                        )
                    )
        elif lead_kind == "redirect":
            for finding in self._findings_matching(policy, findings, "superfície de rotas"):
                extras = finding.get("extras") or {}
                for route in extras.get("routes") or []:
                    url = str(
                        route.get("requested_url")
                        or route.get("probe_url")
                        or route.get("url")
                        or ""
                    ).strip()
                    if not url:
                        continue
                    if _host(str(route.get("url") or "")) != _host(url):
                        detail = "rota saiu para host externo no crawl"
                    else:
                        detail = "rota observada no crawl"
                    _add(
                        _Lead(
                            url=url,
                            detail=detail,
                            session=str(route.get("session") or "anon"),
                        )
                    )
        elif lead_kind == "authn":
            for finding in self._findings_matching(policy, findings, "vetores de entrada"):
                for route in (finding.get("extras") or {}).get("routes") or []:
                    if str(route.get("method") or "GET").upper() != "POST":
                        continue
                    fields = [str(f) for f in route.get("fields") or []]
                    if not any(
                        any(hint in (f or "").lower() for hint in _PASSWORD_HINTS)
                        for f in fields
                    ):
                        continue
                    url = str(route.get("url") or route.get("probe_url") or "").strip()
                    if not url:
                        continue
                    _add(
                        _Lead(
                            url=url,
                            detail="form de login (campo de senha) observado",
                            method="POST",
                            fields=fields,
                            session=str(route.get("session") or "anon"),
                        )
                    )
        elif lead_kind == "api":
            # M8-P1: leads vêm da superfície oficial do spec OpenAPI (M8-P0).
            # Nenhum valor é inventado — a spec só declara nomes de parâmetros,
            # então o probe re-visita o endpoint sem valores (GET, somente
            # leitura) e observa como ele responde a JSON.
            for route in report.api_endpoints:
                url = str(route.get("url") or "").strip()
                if not url.startswith(("http://", "https://")):
                    continue
                params = [str(p) for p in (route.get("params") or [])]
                _add(
                    _Lead(
                        url=url,
                        detail=(
                            f"endpoint {route.get('method')} {route.get('path')} "
                            "da spec OpenAPI observada"
                        ),
                        method=str(route.get("method") or "GET").upper(),
                        fields=params,
                        session=str(route.get("session") or "anon"),
                    )
                )
        elif lead_kind in ("injection", "upload", "csrf"):
            reflection_leads = self._reflection_params(findings)
            for finding in self._findings_matching(policy, findings, "vetores de entrada"):
                for route in (finding.get("extras") or {}).get("routes") or []:
                    url = str(route.get("url") or route.get("probe_url") or "").strip()
                    if not url:
                        continue
                    method = str(route.get("method") or "GET").upper()
                    if lead_kind == "csrf" and method != "POST":
                        continue
                    if lead_kind == "injection":
                        if method != "GET":
                            continue
                        if not reflection_leads.get(_host(url)):
                            continue
                        param, value = reflection_leads[_host(url)]
                        action = urljoin(url, str(route.get("action") or ""))
                        _add(
                            _Lead(
                                url=f"{action}?{urlencode({param: value})}",
                                detail=f"replay do parâmetro observado {param}",
                                param=param,
                                value=value,
                                method="GET",
                                session=str(route.get("session") or "anon"),
                            )
                        )
                    else:
                        _add(
                            _Lead(
                                url=url,
                                detail=f"form {method} observado",
                                method=method,
                                fields=[str(f) for f in route.get("fields") or []],
                                session=str(route.get("session") or "anon"),
                            )
                        )
        return leads

    @staticmethod
    def _findings_matching(
        policy: ProbePolicy, findings: list[dict[str, Any]], category_contains: str | None
    ) -> list[dict[str, Any]]:
        pre = policy.precondition
        matched: list[dict[str, Any]] = []
        for finding in findings:
            title = str(finding.get("title") or "")
            category = str(finding.get("category") or "")
            if pre.title_contains and pre.title_contains.lower() not in title.lower():
                continue
            if pre.category_contains and pre.category_contains.lower() not in category.lower():
                continue
            if category_contains and category_contains.lower() not in category.lower():
                continue
            matched.append(finding)
        return matched

    @staticmethod
    def _reflection_params(findings: list[dict[str, Any]]) -> dict[str, tuple[str, str]]:
        """Primeiro par (param, value) refletido por host, para o replay controlado."""
        by_host: dict[str, tuple[str, str]] = {}
        for finding in findings:
            if "reflexão" not in str(finding.get("category") or "").lower():
                continue
            for ref in (finding.get("extras") or {}).get("reflections") or []:
                url = str(ref.get("probe_url") or ref.get("url") or "")
                host = _host(url)
                param = str(ref.get("param") or "")
                value = str(ref.get("value") or "")
                if host and param and value and host not in by_host:
                    by_host[host] = (param, value)
        return by_host

    # ------------------------------------------------------------------
    # Execução do probe + avaliação de sinal
    # ------------------------------------------------------------------
    def _client_for(self, lead: _Lead) -> ScanHTTPClient:
        """Client do probe: o da sessão do lead (M7-P2) ou o default do run."""
        return self._session_clients.get(lead.session) or self._client

    async def _probe(self, policy: ProbePolicy, lead: _Lead) -> dict[str, Any]:
        """Re-visita o endpoint com o client da sessão observada (M7-P2)."""
        client = self._client_for(lead)
        host = _host(lead.url)
        blocked = await self._robots_blocked(host, lead.url)
        if blocked is not None:
            return self._record(policy, lead, skipped=True, skip_reason=blocked)
        needs_differential = any(
            rule.kind == "login_differential"
            for rule in [*policy.positive_signal, *policy.negative_signal]
        )
        if needs_differential:
            return await self._probe_post(policy, lead)
        try:
            page = await client.get_page(lead.url)
        except ScanError as exc:  # noqa: BLE001 - transcrito como skip auditável
            return self._record(policy, lead, skipped=True, skip_reason=f"unreachable: {exc}")

        page.forms = parse_html(page.url, page.body)["forms"]
        positive, fp, detail = self._evaluate(policy, page, lead)
        return self._record(
            policy,
            lead,
            positive=positive,
            fp=fp,
            status_code=page.status_code,
            detail=detail,
            final_url=page.url,
        )

    async def _probe_post(self, policy: ProbePolicy, lead: _Lead) -> dict[str, Any]:
        """Diferencial P3 (authn): dois envios de login, mesma senha sentinela.

        Re-visita a página do form (uma vez), encontra o form de login fresca e
        envia duas tentativas que diferem apenas no usuário (controles sentinela
        — nunca credenciais reais). Respostas diferentes (status ou corpo)
        indicam que a aplicação discrimina a existência de conta.
        """
        client = self._client_for(lead)
        try:
            page = await client.get_page(lead.url)
        except ScanError as exc:  # noqa: BLE001
            return self._record(policy, lead, skipped=True, skip_reason=f"unreachable: {exc}")

        form = select_login_form(parse_html(page.url, page.body)["forms"])
        if form is None:
            return self._record(
                policy,
                lead,
                positive=False,
                fp=False,
                status_code=page.status_code,
                detail="sinal não confirmado; página fresca sem form de login (campo de senha)",
                final_url=page.url,
            )

        action = urljoin(page.url, form.action or page.url)
        if _host(action) != _host(lead.url):
            return self._record(
                policy,
                lead,
                skipped=True,
                skip_reason=f"action do form fora do host ({_host(action)})",
            )

        try:
            first = await client.post_page(
                action, login_payload(form, _AUTHN_DIFFERENTIAL_USERS[0], _AUTHN_SENTINEL_PASSWORD)
            )
            second = await client.post_page(
                action, login_payload(form, _AUTHN_DIFFERENTIAL_USERS[1], _AUTHN_SENTINEL_PASSWORD)
            )
        except ScanError as exc:  # noqa: BLE001
            return self._record(policy, lead, skipped=True, skip_reason=f"unreachable: {exc}")

        diverged = (
            first.status_code,
            first.body.strip().lower(),
        ) != (
            second.status_code,
            second.body.strip().lower(),
        )
        lead.differential = diverged
        positive, fp, _ = self._evaluate(policy, first, lead)
        detail = (
            "sinal reproduzido (login_differential)" if positive else "sinal não confirmado"
        )
        detail += (
            f"; status {first.status_code} vs {second.status_code}; "
            f"corpo {'divergiu' if diverged else 'idêntico'}"
        )
        if page.url != first.url:
            detail += f"; redirecionou para rede: {_host(first.url)}"
        return self._record(
            policy,
            lead,
            positive=positive,
            fp=fp,
            status_code=first.status_code,
            detail=detail[:300],
            final_url=first.url,
        )

    def _evaluate(
        self, policy: ProbePolicy, page: TargetPage, lead: _Lead
    ) -> tuple[bool, bool, str]:
        """Avalia os sinais da política contra a resposta fresca.

        Um sinal negativo (FP) tem precedência: se ele casa, o probe não é
        considerado positivo mesmo que o positivo também tenha casado.
        """
        fp = any(self._match(rule, page, lead) for rule in policy.negative_signal)
        pos = any(self._match(rule, page, lead) for rule in policy.positive_signal)
        detail = self._detail(policy, page, lead, pos and not fp)
        return (pos and not fp), fp, detail

    def _detail(
        self, policy: ProbePolicy, page: TargetPage, lead: _Lead, positive: bool
    ) -> str:
        state = "sinal reproduzido" if positive else "sinal não confirmado"
        parts = [f"{state} ({policy.class_label})", f"HTTP {page.status_code}"]
        if lead.param and lead.value:
            context = _reflection_context(page.body, lead.value)
            parts.append(f"param={lead.param} contexto={context}")
        if page.url != lead.url:
            parts.append(f"redirecionou para {_host(page.url) or page.url}")
        return "; ".join(parts)[:300]

    def _match(self, rule: SignalRule, page: TargetPage, lead: _Lead) -> bool:
        kind = rule.kind
        if kind == "body_contains":
            return str(rule.value or "").lower() in page.body.lower()
        if kind == "body_none_of":
            values = rule.value if isinstance(rule.value, list) else [rule.value]
            body = page.body.lower()
            return not any(str(v).lower() in body for v in values if v is not None)
        if kind == "status_in":
            values = rule.value if isinstance(rule.value, list) else [rule.value]
            return page.status_code in [int(v) for v in values if v is not None]
        if kind == "reflects_param":
            if not (lead.param and lead.value):
                return False
            return bool(
                re.search(
                    rf"(?<![A-Za-z0-9_]){re.escape(lead.value)}(?![A-Za-z0-9_])",
                    page.body,
                )
            )
        if kind == "redirect_external":
            return bool(page.url) and _host(page.url) != _host(lead.url)
        if kind == "missing_sensitive_field":
            return _has_postonly_form_without_token(page)
        if kind == "file_input_without_accept":
            return _has_file_input_without_accept(page)
        if kind == "login_differential":
            # O diferencial é computado em _probe_post e carregado no lead.
            return lead.differential is True
        if kind == "json_response":
            return _json_value(page.body) is not None
        if kind == "json_has_array":
            return bool(_json_value(page.body)) and _json_has_list(_json_value(page.body))
        if kind == "json_contains":
            # Estrutural (JSON-adaptado): o valor é procurado em chaves e
            # strings do JSON parseado — não em substring do corpo cru.
            return _json_contains(_json_value(page.body), str(rule.value or ""))
        return False

    def _record(
        self,
        policy: ProbePolicy,
        lead: _Lead,
        *,
        skipped: bool = False,
        skip_reason: str | None = None,
        positive: bool = False,
        fp: bool = False,
        status_code: int | None = None,
        detail: str = "",
        final_url: str | None = None,
    ) -> dict[str, Any]:
        return {
            "rule_id": policy.id,
            "policy_version": policy.version,
            "policy_sha256": catalog_digest(policy),
            "priority": policy.priority,
            "class_label": policy.class_label,
            "tool": policy.allowed_probe.tool,
            "method": policy.allowed_probe.method,
            "url": lead.url,
            "final_url": final_url,
            "host": _host(lead.url),
            "session": lead.session,
            "status_code": status_code,
            "positive": bool(positive),
            "fp_matched": bool(fp),
            "skipped": bool(skipped),
            "skip_reason": skip_reason,
            "detail": detail,
            "observed_at": _utcnow(),
        }

    def _behavior_finding(
        self, policy: ProbePolicy, records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        count = len(records)
        title = policy.reporting.title_template.format(
            count=count, class_label=policy.class_label
        )
        lines = [
            f"- {r['url']} [HTTP {r.get('status_code')}] regra {r['rule_id']}@"
            f"{r['policy_version']}: {r.get('detail')}"
            for r in records
        ]
        return {
            "id": None,
            "title": title,
            "description": policy.description,
            "severity": policy.candidate_severity,
            "category": f"{BEHAVIOR_CATEGORY_PREFIX}{policy.class_label}",
            "affected": records[0].get("host") or "unknown",
            "cvss_score": None,
            "cvss_vector": None,
            "cves": [],
            "known_exploits": [],
            "remediation": policy.reporting.remediation,
            "references": policy.reporting.references or ["https://owasp.org/Top10/"],
            "evidence": f"{count} sinal(is) reproduzível(is) sob política:\n"
            + "\n".join(lines),
            "confidence": policy.reporting.confidence,
            "status": "candidate",
            "requires_human_review": policy.requires_hitl,
            "extras": {
                "probes": records,
                "positive_count": count,
                "rule_ids": sorted({r["rule_id"] for r in records}),
                "policy_versions": {r["rule_id"]: r["policy_version"] for r in records},
                "probe_class": policy.class_label,
                "priority": policy.priority,
                "sessions": sorted({r["session"] for r in records}),
            },
        }

    # ------------------------------------------------------------------
    # Controles compartilhados com o scanning ativo
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


_MISSING = object()


def _json_value(body: str) -> Any | None:
    """Corpo parseado como JSON (dict/list); None se não for JSON."""
    try:
        data = json.loads(body)
    except (ValueError, TypeError):
        return None
    return data if isinstance(data, (dict, list)) else None


def _json_has_list(value: Any | None) -> bool:
    """True se o JSON parsed contiver alguma lista (batch/coleção)."""
    if value is None:
        return False
    if isinstance(value, list):
        return True
    if isinstance(value, dict):
        return any(_json_has_list(v) for v in value.values())
    return False


def _json_contains(value: Any | None, needle: str) -> bool:
    """Procura ``needle`` (case-insensitive) em chaves e strings do JSON."""
    if value is None or not needle:
        return False
    target = needle.lower()
    if isinstance(value, str):
        return target in value.lower()
    if isinstance(value, list):
        return any(_json_contains(v, needle) for v in value)
    if isinstance(value, dict):
        for key, item in value.items():
            if target in str(key).lower():
                return True
            if _json_contains(item, needle):
                return True
    return False


def _reflection_context(body: str, value: str) -> str:
    """Classificação grosseira de *onde* o valor observado apareceu.

    Puramente estrutural sobre a resposta real (sem payload): se o valor cai
    dentro de ``<script>`` ou de um atributo HTML, a reflexão é considerada de
    contexto perigoso — o detalhe acompanha a evidência.
    """
    idx = body.find(value)
    if idx < 0:
        return "ausente"
    before = body[max(0, idx - 200) : idx].lower()
    if before.rfind("<script") > before.rfind("</script"):
        return "script"
    if "=" in body[max(0, idx - 40) : idx] and (
        "'" in body[max(0, idx - 40) : idx] or '"' in body[max(0, idx - 40) : idx]
    ):
        return "atributo"
    return "texto"


def _has_file_input_without_accept(page: TargetPage) -> bool:
    for form in page.forms:
        for fld in form.fields:
            if fld.type == "file":
                accept = (fld.accept or "").strip().lower()
                if accept in _BROAD_ACCEPT:
                    return True
    return False


def _has_postonly_form_without_token(page: TargetPage) -> bool:
    for form in page.forms:
        if form.method != "post":
            continue
        has_editable = any(
            f.type in _EDITABLE_TYPES or f.type in ("password", "file") for f in form.fields
        )
        if not has_editable:
            continue
        names = [(f.name or "").lower() for f in form.fields]
        if not any(any(hint in name for hint in _TOKEN_NAME_HINTS) for name in names):
            return True
    return False


def build_probe_engine(client: ScanHTTPClient | None = None) -> ProbeEngine:
    """Instancia o motor a partir das settings (``PROBE_*``) e do catálogo."""
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
    return ProbeEngine(
        client=client,
        enabled=settings.probe_enabled,
        max_probes=settings.probe_max_per_run,
        max_per_endpoint=settings.probe_max_per_endpoint,
        respect_robots=settings.probe_respect_robots,
        default_classes=settings.probe_classes_default,
    )


def verbose_error_markers() -> tuple[str, ...]:
    """Marcadores de erro verboso reutilizados do detector do scan (M6 P0)."""
    return tuple(_VERBOSE_ERROR_MARKERS)
