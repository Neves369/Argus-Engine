"""Derive genuine, evidence-grounded findings from active-scan results.

Mirrors ``app/services/source_findings.py``: every finding produced here must
trace back to an actual observed response (status code, header, cookie flag,
form). Nothing is inferred, fabricated, or correlated to a CVE without a real
lookup — scan results are leads for a human operator, always
``status="candidate"`` and ``requires_human_review=True``.

Report polish (M1): per-page input-vector and reflection detections are
aggregated into a single finding per run with the detailed route list kept in
``extras`` (so the Carro can still re-probe each route live); a route map
separates application routes from static assets. Other findings stay
deduplicated by title as before.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.scanning.detectors import _finding, detect_on_page
from app.scanning.parsers import parse_html
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage

_FORM_TITLE = "Formulários com entrada de dados encontrados"
_REFLECTION_TITLE = "Parâmetro refletido no corpo da resposta"
_WEBSOCKET_TITLE = "WebSocket endpoint detectado (upgrade)"
AGGREGATE_FORM_TITLE = "formulário(s) com entrada de dados observados no crawl"
AGGREGATE_REFLECTION_TITLE = "parâmetro(s) refletido(s) no corpo da resposta"

_STATIC_EXTENSIONS = (
    ".css",
    ".js",
    ".ico",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".webp",
    ".woff",
    ".woff2",
    ".ttf",
    ".map",
)
_STATIC_NAMES = ("favicon.ico",)


def derive_findings_from_scan(report: ScanReport) -> list[dict[str, Any]]:
    """Turn observed scan pages into candidate findings, deduped by title.

    Input-vector (forms) and reflected-parameter detections are aggregated per
    run — the title carries the count and ``extras`` keeps per-route detail so
    the Carro can re-probe each lead. Verbose errors keep their URL-specific
    titles; misconfig findings are deduped by title (one per host).
    """
    if not report.pages and not report.api_endpoints and not report.graphql_endpoints:
        return []

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_title: dict[str, dict[str, Any]] = {}
    form_routes: list[dict[str, Any]] = []
    reflections: list[dict[str, Any]] = []
    websocket_endpoints: list[dict[str, Any]] = []

    for page in report.pages:
        for finding in detect_on_page(page):
            finding["probe_url"] = page.url
            finding["session"] = page.session
            title = finding["title"]
            if title == _FORM_TITLE:
                form_routes.extend((finding.get("extras") or {}).get("routes", []))
                seen.add(title)
                continue
            if title == _REFLECTION_TITLE:
                for ref in (finding.get("extras") or {}).get("reflections", []):
                    ref.setdefault("probe_url", page.url)
                    ref.setdefault("session", page.session)
                reflections.extend((finding.get("extras") or {}).get("reflections", []))
                seen.add(title)
                continue
            if title == _WEBSOCKET_TITLE:
                for url in (finding.get("extras") or {}).get("websocket_urls") or []:
                    websocket_endpoints.append(
                        {"url": url, "page_url": page.url, "session": page.session}
                    )
                seen.add(title)
                continue
            if title in seen:
                # Mesma URL observada sob outra sessão: o finding já existe,
                # então registra a sessão adicional (probes por papel, M7-P2).
                existing = per_title.get(title)
                if existing is not None:
                    sessions = existing.setdefault("sessions", [existing["session"]])
                    if page.session not in sessions:
                        sessions.append(page.session)
                continue
            seen.add(title)
            per_title[title] = finding
            findings.append(finding)

    aggregates: list[dict[str, Any]] = []
    if form_routes:
        aggregates.append(_aggregate_forms(form_routes))
    if reflections:
        aggregates.append(_aggregate_reflections(reflections))
    if websocket_endpoints:
        aggregates.append(_aggregate_websockets(websocket_endpoints))
    route_map = _route_map_finding(report)
    if route_map is not None:
        aggregates.append(route_map)
    api_surface = _api_surface_finding(report)
    if api_surface is not None:
        aggregates.append(api_surface)
    graphql_surface = _graphql_surface_finding(report)
    if graphql_surface is not None:
        aggregates.append(graphql_surface)

    return [*findings, *aggregates, *_session_access_findings(report)]


def _aggregate_forms(routes: list[dict[str, Any]]) -> dict[str, Any]:
    """One per-run finding for every observed input form (report polish 1.1)."""
    total = len(routes)
    distinct_urls = len({r.get("url") for r in routes})
    lines = []
    for route in routes:
        action = urlparse(route.get("action") or route.get("url") or "").path or "/"
        fields = route.get("fields") or []
        sensitive = route.get("sensitive_fields") or []
        lines.append(
            f"- {action} | {route.get('method', 'GET')} | "
            f"fields=[{', '.join(fields)}]" + (
                f" | sensíveis=[{', '.join(sensitive)}]" if sensitive else ""
            )
        )
    host = _routes_host(routes)
    return _finding(
        title=f"{total} {AGGREGATE_FORM_TITLE}",
        description=(
            "O crawl observou formulários com campos de entrada em endpoints "
            "da aplicação. Cada um é um vetor em que o tratamento de entrada "
            "precisa ser revisado manualmente — nenhum teste é executado; é "
            "um lead observacional de superfície. O detalhe por rota fica na "
            "evidência e em ``extras`` para re-prova ao vivo."
        ),
        severity="info",
        category="Aplicação / vetores de entrada",
        affected=host,
        evidence=f"{total} formulário(s) em {distinct_urls} rota(s):\n" + "\n".join(lines),
        remediation=(
            "Revise manualmente o tratamento de entrada destes endpoints "
            "(validação, parametrização e codificação de saída)."
        ),
        confidence=0.5,
        extras={
            "routes": routes,
            "form_count": total,
            "route_count": distinct_urls,
        },
    )


def _aggregate_reflections(reflections: list[dict[str, Any]]) -> dict[str, Any]:
    """One per-run finding for every reflected parameter (report polish 2.3)."""
    count = len(reflections)
    lines = [
        f"- {r.get('url') or r.get('probe_url','')} ({r.get('param')}={r.get('value')})"
        for r in reflections
    ]
    return _finding(
        title=f"{count} {AGGREGATE_REFLECTION_TITLE}",
        description=(
            "Valores de parâmetros de URL observados pelo crawl aparecem "
            "integralmente no corpo da resposta. Sinal observacional de "
            "reflexão sem processamento — lead para revisão manual, sem "
            "payload. O detalhe por parâmetro fica em ``extras`` para re-prova."
        ),
        severity="info",
        category="Aplicação / reflexão observada",
        affected=_reflections_host(reflections),
        evidence=f"{count} reflexão(ões):\n" + "\n".join(lines),
        remediation=(
            "Revise manualmente como estes parâmetros são refletidos e "
            "codifique a saída antes de devolver ao navegador."
        ),
        confidence=0.5,
        extras={"reflections": reflections, "reflection_count": count},
    )


def _aggregate_websockets(endpoints: list[dict[str, Any]]) -> dict[str, Any]:
    """One per-run finding for every observed WebSocket endpoint (M8-P3)."""
    count = len(endpoints)
    lines = [
        f"- {e['url']} (observado em {e['page_url']})" for e in endpoints
    ]
    sessions = sorted({e.get("session") or "anon" for e in endpoints})
    return _finding(
        title=f"{count} endpoint(s) WebSocket detectado(s)",
        description=(
            "O crawl observou referências a endpoints WebSocket (header de "
            "upgrade ou ``ws://``/``wss://``/``new WebSocket(...)`` no HTML/JS). "
            "Fingerprint de superfície apenas — nenhuma handshake ou teste "
            "profundo é executado nesta etapa."
        ),
        severity="info",
        category="Aplicação / superfície de API",
        affected=_routes_host(endpoints),
        evidence=f"{count} endpoint(s) WebSocket:\n" + "\n".join(lines),
        remediation=(
            "Revise a exposição dos endpoints WebSocket (autenticação, origem e "
            "protocolo de mensagens)."
        ),
        confidence=0.5,
        extras={"endpoints": endpoints, "endpoint_count": count, "sessions": sessions},
    )


def _route_map_finding(report: ScanReport) -> dict[str, Any] | None:
    """Route map: app routes vs static assets, labs first (report polish 1.2)."""
    if not report.pages:
        return None
    app_pages: list[tuple[TargetPage, str]] = []
    static_pages: list[tuple[TargetPage, str]] = []
    for page in report.pages:
        path = urlparse(page.url).path or "/"
        title = parse_html(page.url, page.body)["title"]
        if _is_static(path):
            static_pages.append((page, title))
        else:
            app_pages.append((page, title))

    if not app_pages and not static_pages:
        return None

    app_count = len(app_pages)
    static_count = len(static_pages)
    lines: list[str] = []
    for page, title in sorted(app_pages, key=lambda item: (_route_rank(item[0]), item[0].url)):
        path = urlparse(page.url).path or "/"
        detail = f"GET {path} -> {page.status_code}"
        if title:
            detail += f" ({title})"
        lines.append(f"- {detail}")
    for page, _title in sorted(static_pages, key=lambda item: item[0].url):
        path = urlparse(page.url).path or "/"
        lines.append(f"- {path} -> {page.status_code} (estático)")

    title = f"{app_count} rota(s) de aplicação descobertas"
    if static_count:
        title += f" + {static_count} estático(s)"
    evidence = "\n".join(lines)[:2000]
    host = app_pages[0][0].host if app_pages else static_pages[0][0].host
    return _finding(
        title=title,
        description=(
            "O crawl mapeou rotas de aplicação (páginas HTML servidas pelo "
            "host) e ativos estáticos referenciados. A ordem de apresentação "
            "privilegia páginas de lab, depois setup/login/security e, por fim, "
            "estáticos. Nenhum fuzz é executado — apenas o crawl "
            "evidence-grounded."
        ),
        severity="info",
        category="Aplicação / superfície de rotas",
        affected=host,
        evidence=evidence,
        remediation=(
            "Use o mapa para priorizar a revisão manual das rotas de "
            "aplicação antes de considerar ativos estáticos."
        ),
        confidence=0.6,
        extras={
            "routes": [
                {
                    "url": page.url,
                    "status_code": page.status_code,
                    "title": title,
                    "static": False,
                    "probe_url": page.url,
                    "requested_url": page.requested_url or page.url,
                    "session": page.session,
                }
                for page, title in app_pages
            ],
            "static_routes": [
                {"url": page.url, "status_code": page.status_code, "static": True}
                for page, _title in static_pages
            ],
            "app_route_count": app_count,
            "static_count": static_count,
        },
    )


def _api_surface_finding(report: ScanReport) -> dict[str, Any] | None:
    """API surface from an observed OpenAPI/Swagger spec (M8-P0).

    The spec is the operator's own official surface — no endpoint is invented,
    no enumeration is performed. The report maps method/path/params exactly as
    declared, filtered to the target host, and labels the session that could
    retrieve the spec.
    """
    endpoints = list(report.api_endpoints)
    if not endpoints:
        return None
    host = report.target
    distinct_paths = len({e["path"] for e in endpoints})
    sessions = sorted({e.get("session") or "anon" for e in endpoints})
    methods = sorted({e["method"] for e in endpoints})
    spec = report.api_spec or {}
    lines = [
        f"- {e['method']} {e['path']}"
        + (f" | params=[{', '.join(e['params'])}]" if e.get("params") else "")
        + f" | sessão {e.get('session') or 'anon'}"
        for e in sorted(endpoints, key=lambda ep: (ep["path"], ep["method"]))
    ]
    return _finding(
        title=f"{len(endpoints)} endpoint(s) de API mapeados (OpenAPI)",
        description=(
            "A aplicação publica uma especificação OpenAPI/Swagger que o scan "
            "observou e validou (fail-closed). Os endpoints listados são a "
            "superfície oficial declarada pelo próprio alvo — nenhum caminho é "
            "inventado nem enumerado. O detalhe por endpoint/método/parâmetros "
            "fica em ``extras`` para re-prova ao vivo e para as sondas de "
            "política (M8-P1)."
        ),
        severity="info",
        category="Aplicação / superfície de API",
        affected=host,
        evidence="\n".join(lines)[:2000],
        remediation=(
            "Use a superfície para revisar manualmente a exposição de cada "
            "endpoint (autenticação, autorização e tratamento de entrada)."
        ),
        confidence=0.6,
        extras={
            "endpoints": endpoints,
            "endpoint_count": len(endpoints),
            "distinct_paths": distinct_paths,
            "methods": methods,
            "sessions": sessions,
            "spec_url": spec.get("url"),
            "spec_sha256": spec.get("sha256"),
        },
    )


def _graphql_surface_finding(report: ScanReport) -> dict[str, Any] | None:
    """GraphQL surface from passive endpoint detection (M8-P2).

    Endpoints detectados por caminho canônico ou referência em HTML/JS são a
    superfície do próprio alvo — nenhuma introspecção acontece aqui (isso é um
    probe sob política). Cada endpoint fica em ``extras`` para servir de lead à
    política de introspecção (``graphql_introspection_p1``).
    """
    endpoints = list(report.graphql_endpoints)
    if not endpoints:
        return None
    host = report.target
    sessions = sorted({e.get("session") or "anon" for e in endpoints})
    lines = [
        f"- {e['url']} (detecção: {e.get('detected_by') or 'path'})"
        + f" | sessão {e.get('session') or 'anon'}"
        for e in sorted(endpoints, key=lambda ep: ep["url"])
    ]
    return _finding(
        title=f"{len(endpoints)} endpoint(s) GraphQL detectado(s)",
        description=(
            "O alvo expõe um endpoint GraphQL detectado de forma passiva "
            "(caminho canônico ou referência em HTML/JS). Nenhuma introspecção "
            "foi executada aqui — a exposição do schema é avaliada apenas sob "
            "política autorizada (probe de introspecção, M8-P2). O detalhe por "
            "endpoint fica em ``extras``."
        ),
        severity="info",
        category="Aplicação / superfície de API",
        affected=host,
        evidence="\n".join(lines)[:2000],
        remediation=(
            "Revise a exposição do endpoint GraphQL: exija autenticação quando "
            "aplicável e desabilite a introspecção em produção se não for "
            "necessária."
        ),
        confidence=0.5,
        extras={
            "endpoints": endpoints,
            "endpoint_count": len(endpoints),
            "sessions": sessions,
        },
    )


def _is_static(path: str) -> bool:
    lower = path.lower()
    if lower.rstrip("/").rsplit("/", 1)[-1] in _STATIC_NAMES:
        return True
    return lower.endswith(_STATIC_EXTENSIONS)


def _route_rank(page: TargetPage) -> int:
    path = urlparse(page.url).path or "/"
    if path.startswith("/vulnerabilities/"):
        return 0
    if path in ("/setup.php", "/login.php") or path.startswith(
        ("/security/", "/instructions.php", "/logout.php")
    ):
        return 1
    return 2


def _routes_host(routes: list[dict[str, Any]]) -> str:
    for route in routes:
        host = urlparse(route.get("url") or "").netloc
        if host:
            return host
    return "unknown"


def _reflections_host(reflections: list[dict[str, Any]]) -> str:
    for ref in reflections:
        host = urlparse(ref.get("url") or ref.get("probe_url") or "").netloc
        if host:
            return host
    return "unknown"


def _anon_reaches(probe: dict[str, Any], base: str) -> bool:
    """Did the anonymous baseline really see the base URL itself?

    A 2xx final response is not enough: if the anonymous request was pulled
    away from the base (redirect to the login page, for example), the base
    content was NOT observed anonymously even when the final status was 200.
    """
    status = probe.get("status_code")
    if status is None or not (200 <= status < 300):
        return False
    final = probe.get("final_url") or ""
    if not final:
        return False
    base_parts = urlparse(base)
    final_parts = urlparse(final)
    if final_parts.netloc != base_parts.netloc:
        return False
    base_path = base_parts.path.rstrip("/") or "/"
    final_path = final_parts.path.rstrip("/") or "/"
    return base_path == final_path


def _successful_sessions(report: ScanReport) -> list[dict[str, Any]]:
    return [
        s
        for s in report.sessions
        if str(s.get("name") or "") and s.get("auth_status") == "success"
    ]


def _pages_of(pages: list[TargetPage], session: str) -> list[TargetPage]:
    return [p for p in pages if p.session == session]


def _reaches_status(status: int) -> bool:
    return 200 <= status < 300


def _session_access_findings(report: ScanReport) -> list[dict[str, Any]]:
    """Access-difference observations across sessions (M7).

    Two evidence-grounded signals, both observational (no enumeration):
    1. Anon-blind (M7-P0): a base URL is reached by some session but the
       anonymous baseline does not reach it (non-2xx or redirected away).
    2. Cross-session (M7-P1): a route observed under multiple profiles is
       reachable under one session and not under another (e.g. admin vs user).
    """
    sessions = _successful_sessions(report)
    if not sessions:
        return []
    findings: list[dict[str, Any]] = []

    anon_diffs = _anon_blind_diffs(report, sessions)
    for session in sessions:
        diffs = anon_diffs.get(str(session["name"]) or "", [])
        if not diffs:
            continue
        name = session["name"]
        lines = [
            f"- GET {d['url']} -> {d['auth_status']} (sessão {name}); anônimo -> "
            f"{d['anon_status']} {d.get('anon_final_url')}"
            for d in diffs
        ]
        title = (
            "Conteúdo visível apenas em sessão autenticada (controle de acesso)"
            if name == "user"
            else f"Conteúdo visível apenas na sessão {name} (controle de acesso)"
        )
        findings.append(
            _finding(
                title=title,
                description=(
                    "O crawl descobriu conteúdo (sob login dinâmico) que uma "
                    "requisição anônima ao mesmo endereço não alcançou. Sinal "
                    "observacional de controle de acesso por sessão — o "
                    "relatório apenas constata a diferença; nenhum bypass é "
                    "testado. O resultado é um lead para revisão manual."
                ),
                severity="info",
                category="Aplicação / controle de acesso",
                affected=report.target,
                evidence="\n".join(lines)[:2000],
                remediation=(
                    "Revise manualmente se a proteção de autenticação destas "
                    "rotas é intencional e se o conteúdo deve mesmo ser "
                    "restrito à sessão autenticada."
                ),
                confidence=0.4,
                extras={
                    "sessions": list(report.sessions),
                    "asymmetric": diffs,
                    "asymmetric_count": len(diffs),
                },
            )
        )

    routes_diff = _cross_session_diffs(report, sessions)
    if routes_diff:
        lines = [
            f"- {r['url']} -> {', '.join(r['accessible_in'])} "
            f"(não em {', '.join(r['not_in'])})"
            for r in routes_diff
        ]
        findings.append(
            _finding(
                title="Acesso distinto entre sessões (controle de acesso)",
                description=(
                    "Rotas observadas sob mais de uma sessão (perfil) foram "
                    "alcançadas em um papel e não em outro, ou o inverso. O "
                    "relatório apenas constata a diferença entre as sessões "
                    "observadas — sem bypass, sem enumeração. Lead para "
                    "revisão manual de autorização por papel."
                ),
                severity="info",
                category="Aplicação / controle de acesso",
                affected=report.target,
                evidence="\n".join(lines)[:2000],
                remediation=(
                    "Revise manualmente a matriz de autorização por papel "
                    "(ou authz por rota) destes endpoints."
                ),
                confidence=0.4,
                extras={
                    "sessions": list(report.sessions),
                    "routes": routes_diff,
                    "route_count": len(routes_diff),
                },
            )
        )
    return findings


def _anon_blind_diffs(
    report: ScanReport, sessions: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Base URLs reachable in a session but not by the anonymous baseline."""
    by_session: dict[str, list[dict[str, Any]]] = {}
    for session in sessions:
        name = str(session["name"])
        pages = _pages_of(report.pages, name)
        for probe in report.anon_probe:
            base = probe.get("url")
            if not base or _anon_reaches(probe, base):
                continue
            page = next(
                (p for p in pages if p.url == base or (p.requested_url or "") == base),
                None,
            )
            if page is None or not _reaches_status(page.status_code):
                continue
            by_session.setdefault(name, []).append(
                {
                    "url": base,
                    "session": name,
                    "anon_status": probe.get("status_code"),
                    "anon_final_url": probe.get("final_url"),
                    "auth_status": page.status_code,
                }
            )
    return by_session


def _cross_session_diffs(
    report: ScanReport, sessions: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Routes reachable under one observed session but not another."""
    if len(sessions) < 2:
        return []
    names = [str(s["name"]) for s in sessions]
    reachable_by_url: dict[str, list[str]] = {}
    observed_by_url: dict[str, list[str]] = {}
    for name in names:
        for page in _pages_of(report.pages, name):
            if not page.url:
                continue
            observed_by_url.setdefault(page.url, []).append(name)
            if _reaches_status(page.status_code):
                reachable_by_url.setdefault(page.url, []).append(name)
    diffs: list[dict[str, Any]] = []
    for url, observed in observed_by_url.items():
        blocked = [n for n in names if n in observed and n not in reachable_by_url.get(url, [])]
        reachable = [n for n in names if n in reachable_by_url.get(url, [])]
        if reachable and blocked:
            diffs.append(
                {
                    "url": url,
                    "accessible_in": sorted(reachable),
                    "not_in": sorted(blocked),
                }
            )
    diffs.sort(key=lambda d: (d["url"]))
    return diffs
