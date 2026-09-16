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


def _discovered_routes_finding(report: ScanReport) -> dict[str, Any] | None:
    """Report-level lead: distinct internal paths/modules observed by the crawl."""
    paths: list[str] = []
    for page in report.pages:
        path = urlparse(page.url).path.rstrip("/") or "/"
        if path not in paths:
            paths.append(path)
    if len(paths) <= 1:
        return None
    sample = paths[:20]
    more = f" (+{len(paths) - len(sample)} outro(s))" if len(paths) > len(sample) else ""
    return {
        "id": None,
        "title": f"{len(paths)} módulo(s)/rota(s) internos descobertos durante o crawl",
        "description": (
            "O crawl observacional encontrou páginas/rotas internas do mesmo "
            "host além da raiz. Cada módulo amplia a superfície de aplicação e "
            "vale revisão manual de tratamento de entrada e autorização. "
            "Nenhum teste foi executado — são apenas destinos observados."
        ),
        "severity": "info",
        "category": "Aplicação (módulos/rotas observados)",
        "affected": report.target,
        "cvss_score": None,
        "cvss_vector": None,
        "cves": [],
        "known_exploits": [],
        "remediation": (
            "Revise cada módulo descoberto: confirme se deve estar acessível, "
            "se exige autenticação e se o tratamento de entrada é adequado."
        ),
        "references": ["https://owasp.org/Top10/"],
        "evidence": "Rotas: " + ", ".join(sample) + more,
        "confidence": 0.7,
        "status": "candidate",
        "requires_human_review": True,
    }


def derive_findings_from_scan(report: ScanReport) -> list[dict[str, Any]]:
    """Turn observed scan pages into candidate findings, deduped by title.

    Input-vector (forms) and reflected-parameter detections are aggregated per
    run — the title carries the count and ``extras`` keeps per-route detail so
    the Carro can re-probe each lead. Verbose errors keep their URL-specific
    titles; misconfig findings are deduped by title (one per host).
    """
    if not report.pages:
        return []

    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    form_routes: list[dict[str, Any]] = []
    reflections: list[dict[str, Any]] = []

    for page in report.pages:
        for finding in detect_on_page(page):
            finding["probe_url"] = page.url
            title = finding["title"]
            if title == _FORM_TITLE:
                form_routes.extend((finding.get("extras") or {}).get("routes", []))
                seen.add(title)
                continue
            if title == _REFLECTION_TITLE:
                for ref in (finding.get("extras") or {}).get("reflections", []):
                    ref.setdefault("probe_url", page.url)
                reflections.extend((finding.get("extras") or {}).get("reflections", []))
                seen.add(title)
                continue
            if title in seen:
                continue
            seen.add(title)
            findings.append(finding)

    aggregates: list[dict[str, Any]] = []
    if form_routes:
        aggregates.append(_aggregate_forms(form_routes))
    if reflections:
        aggregates.append(_aggregate_reflections(reflections))
    route_map = _route_map_finding(report)
    if route_map is not None:
        aggregates.append(route_map)

    return [*findings, *aggregates]


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
