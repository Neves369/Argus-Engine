"""Derive genuine, evidence-grounded findings from active-scan results.

Mirrors ``app/services/source_findings.py``: every finding produced here must
trace back to an actual observed response (status code, header, cookie flag,
form). Nothing is inferred, fabricated, or correlated to a CVE without a real
lookup — scan results are leads for a human operator, always
``status="candidate"`` and ``requires_human_review=True``.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.scanning.detectors import detect_on_page
from app.scanning.service import ScanReport


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
    """Turn observed scan pages into candidate findings, deduped by title."""
    findings: list[dict[str, Any]] = []
    seen: set[str] = set()
    for page in report.pages:
        for finding in detect_on_page(page):
            if finding["title"] in seen:
                continue
            seen.add(finding["title"])
            # The page that produced the finding, so the Carro can re-probe it
            # live later (verification probes — Etapa 15).
            finding["probe_url"] = page.url
            findings.append(finding)
    routes = _discovered_routes_finding(report)
    if routes is not None and routes["title"] not in seen:
        findings.append(routes)
    return findings