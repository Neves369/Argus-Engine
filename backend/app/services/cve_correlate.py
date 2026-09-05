"""Best-effort correlation of scanned products to real CVEs and known exploits.

Closes the tool-integration seam: the scanner fingerprints things like a
``Server`` banner (``Apache/2.4.49``) but never correlates them to known
vulnerabilities. This module does that correlation using only read-only public
feeds, all already declared in ``sources.json``:

#. NVD keyword search on the product + version (candidates, with CVSS and
   CISA-exploitation metadata embedded in each NVD record);
#. CVE.report per-ID enrichment (best-effort — extra references and KEV/EPSS
   when available);
#. the CISA Known Exploited Vulnerabilities (KEV) catalog, matched by CVE ID,
   as the ``known_exploits`` signal.

Honesty rules (mirroring ``app/services/source_findings.py``):

- keyword correlation is a *textual lead*, never a confirmed vulnerability —
  every finding is ``status="candidate"`` with ``requires_human_review=True``
  and a confidence below the validation threshold;
- a source that is unreachable, rate-limited or returning simulated data
  (no network / no key) contributes nothing — no value is fabricated;
- nothing here drives execution; it only enriches reporting.

Public API: ``correlate_scan_report`` (used by ``HermitAgent``) and
``correlate_product_cves`` (unit-testable standalone).
"""

from __future__ import annotations

import re
from typing import Any

from app.scanning.service import ScanReport

_MAX_ENRICH_PER_PRODUCT = 3
_SERVER_BANNER_RE = re.compile(
    r"^(?P<product>[A-Za-z0-9._-]+)/(?P<version>[0-9]+(?:\.[0-9]+)*(?:[A-Za-z0-9._-]*))"
)
_PRODUCT_ALIASES = {
    "apache": "apache http server",
    "iis": "microsoft iis",
    "microsoft-iis": "microsoft iis",
    "nginx": "nginx",
}
_SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

_OK_STATUSES = ("ok", "cache")


def product_from_banner(banner: str) -> tuple[str, str | None] | None:
    """Parse ``Apache/2.4.49 (Ubuntu)`` into (product, version).

    Returns ``None`` when the banner carries no version — correlation without a
    version is pure noise (a bare product name returns thousands of unrelated
    CVEs). Product names are normalized (``apache`` -> ``apache http server``)
    for a tighter NVD keyword match.
    """
    match = _SERVER_BANNER_RE.match((banner or "").strip())
    if match is None:
        return None
    product = match.group("product").lower()
    version = match.group("version") or None
    return _PRODUCT_ALIASES.get(product, product), version


def _build_keyword(product: str, version: str | None) -> str:
    return f"{product} {version}".strip() if version else product


async def _safe_query(service: Any, name: str, params: dict[str, Any]) -> dict[str, Any] | None:
    """Query a source, degrading to ``None`` on blocking failures.

    ``DataSourceService.query`` raises ``DataSourceError`` on rate-limit
    violations and missing-config cases; a correlation must never break the
    run it is part of.
    """
    from app.sources.service import DataSourceError

    try:
        return await service.query(name, params)
    except DataSourceError:
        return None


def _is_ok(result: dict[str, Any] | None) -> bool:
    return isinstance(result, dict) and result.get("status") in _OK_STATUSES


def _cvss(cve: dict[str, Any]) -> tuple[float | None, str | None, str | None]:
    """Extract the best available CVSS (v3.1 > v3.0 > v2) from an NVD record.

    Returns ``(base_score, base_severity, vector_string)`` — any of them may be
    ``None`` when the record was never analyzed by NVD.
    """
    metrics = cve.get("metrics")
    if not isinstance(metrics, dict):
        return None, None, None
    for key in ("cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        entries = metrics.get(key)
        if not isinstance(entries, list) or not entries:
            continue
        entry = entries[0]
        data = entry.get("cvssData") if isinstance(entry, dict) else None
        if not isinstance(data, dict):
            continue
        return data.get("baseScore"), data.get("baseSeverity"), data.get("vectorString")
    return None, None, None


def _english_description(cve: dict[str, Any]) -> str | None:
    descriptions = cve.get("descriptions")
    if not isinstance(descriptions, list):
        return None
    for item in descriptions:
        if (
            isinstance(item, dict)
            and item.get("lang") == "en"
            and isinstance(item.get("value"), str)
        ):
            return item["value"]
    return None


def _references(cve: dict[str, Any]) -> list[str]:
    references = cve.get("references")
    if not isinstance(references, list):
        return []
    return [
        ref["url"]
        for ref in references
        if isinstance(ref, dict) and isinstance(ref.get("url"), str)
    ]


def _nvd_candidates(data: Any) -> list[dict[str, Any]]:
    """Normalize an NVD keyword-search payload into correlation candidates.

    Returns an empty list for an unknown/unrecognized response shape — nothing
    is guessed at, mirroring the extractors in ``source_findings``.
    """
    if not isinstance(data, dict):
        return []
    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        return []
    candidates: list[dict[str, Any]] = []
    for item in vulnerabilities:
        cve = item.get("cve") if isinstance(item, dict) else None
        if not isinstance(cve, dict):
            continue
        cve_id = cve.get("id")
        if not isinstance(cve_id, str):
            continue
        score, severity, vector = _cvss(cve)
        candidates.append(
            {
                "cve_id": cve_id,
                "cvss_score": score,
                "cvss_vector": vector,
                "severity": _normalize_severity(severity),
                "description": _english_description(cve),
                "references": _references(cve),
                # CISA exploitation metadata embedded in the NVD record.
                "kev_from_nvd": bool(cve.get("cisaExploitAdd")),
                "kev_name": cve.get("cisaVulnerabilityName"),
                "kev_added": cve.get("cisaExploitAdd"),
                # Filled in later by the KEV catalog / cve.report enrichment.
                "kev_from_catalog": False,
                "kev_from_report": False,
                "kev_ransomware": False,
            }
        )
    return candidates


def _normalize_severity(value: Any) -> str:
    """Map NVD's uppercase severity labels to the report's lowercase set."""
    if not isinstance(value, str):
        return "info"
    return value.lower() if value.lower() in _SEVERITY_RANK else "info"


def _kev_map(data: Any) -> dict[str, dict[str, Any]]:
    """Index the CISA KEV catalog by CVE ID. Empty for unknown shapes."""
    if not isinstance(data, dict):
        return {}
    vulnerabilities = data.get("vulnerabilities")
    if not isinstance(vulnerabilities, list):
        return {}
    index: dict[str, dict[str, Any]] = {}
    for entry in vulnerabilities:
        if isinstance(entry, dict) and isinstance(entry.get("cveID"), str):
            index[entry["cveID"]] = entry
    return index


def _apply_kev(candidate: dict[str, Any], kev_map: dict[str, dict[str, Any]]) -> None:
    """Mark the candidate with catalog evidence of active exploitation."""
    entry = kev_map.get(candidate["cve_id"])
    if not isinstance(entry, dict):
        return
    candidate["kev_from_catalog"] = True
    candidate["kev_name"] = entry.get("vulnerabilityName") or candidate["kev_name"]
    candidate["kev_added"] = entry.get("dateAdded") or candidate["kev_added"]
    candidate["kev_ransomware"] = entry.get("knownRansomwareCampaignUse") == "Known"


async def _enrich_cve_report(candidate: dict[str, Any], service: Any) -> None:
    """Best-effort per-ID enrichment from cve.report (extra refs + KEV/EPSS)."""
    result = await _safe_query(service, "cve_report", {"query": candidate["cve_id"]})
    if not _is_ok(result):
        return
    data = result.get("data")
    if not isinstance(data, dict):
        return
    enrichments = data.get("enrichments")
    if isinstance(enrichments, dict) and isinstance(enrichments.get("KEV"), dict):
        candidate["kev_from_report"] = True
    references = data.get("references")
    if isinstance(references, list):
        for ref in references:
            url = ref if isinstance(ref, str) else ref.get("url") if isinstance(ref, dict) else None
            if isinstance(url, str) and url not in candidate["references"]:
                candidate["references"].append(url)


def _worst_severity(candidates: list[dict[str, Any]]) -> tuple[str, float | None, str | None]:
    worst = "info"
    max_score: float | None = None
    vector: str | None = None
    for candidate in candidates:
        score = candidate.get("cvss_score")
        if isinstance(score, (int, float)) and (max_score is None or score > max_score):
            max_score = score
            vector = candidate.get("cvss_vector")
        if _SEVERITY_RANK[candidate["severity"]] > _SEVERITY_RANK[worst]:
            worst = candidate["severity"]
    return worst, max_score, vector


def _known_exploits(candidates: list[dict[str, Any]]) -> list[str]:
    exploits: list[str] = []
    for candidate in candidates:
        in_kev = (
            candidate["kev_from_catalog"]
            or candidate["kev_from_report"]
            or candidate["kev_from_nvd"]
        )
        if not in_kev:
            continue
        detail = f"CVE {candidate['cve_id']}"
        name = candidate.get("kev_name")
        if isinstance(name, str) and name:
            detail = f"{name} ({candidate['cve_id']})"
        if candidate["kev_ransomware"]:
            detail += " — campanha de ransomware conhecida"
        exploits.append(f"Exploração ativa confirmada para {detail} (CISA KEV)")
    return exploits


def _build_finding(
    product: str,
    version: str | None,
    keyword: str,
    candidates: list[dict[str, Any]],
    nvd_data: Any,
) -> dict[str, Any]:
    display = f"{product} {version}".strip() if version else product
    cve_ids = [c["cve_id"] for c in candidates]
    severity, cvss_score, cvss_vector = _worst_severity(candidates)
    exploits = _known_exploits(candidates)
    references: list[str] = []
    for candidate in candidates:
        for url in candidate["references"]:
            if url not in references:
                references.append(url)
    references = references[:10]

    total = nvd_data.get("totalResults") if isinstance(nvd_data, dict) else None

    return {
        "id": None,
        "title": f"{len(candidates)} CVE(s) correlacionado(s) para {display}",
        "description": (
            f"O fingerprint do alvo corresponde a '{keyword}'. A busca por "
            "palavra-chave no NVD retornou os CVEs listados abaixo. Isto é uma "
            "correspondência textual entre o identificador observado e a base "
            "pública de CVEs — não confirma que a versão real em produção é "
            "vulnerável. Valide manualmente antes de qualquer ação."
        ),
        "severity": severity,
        "category": "A06:2021 Vulnerable and Outdated Components",
        "affected": display,
        "cvss_score": cvss_score,
        "cvss_vector": cvss_vector,
        "cves": cve_ids,
        "known_exploits": exploits,
        "remediation": (
            "Valide a versão real em produção contra o advisory de cada CVE "
            "(a correspondência é textual, não confirmada) e planeje "
            "atualização/atenuação quando aplicável."
        ),
        "references": references,
        "evidence": (
            f"NVD keywordSearch('{keyword}') -> "
            f"{total if total is not None else len(cve_ids)} resultado(s); "
            f"{len(candidates)} candidato(s)"
        ),
        "confidence": round(min(0.5, 0.35 + 0.05 * len(candidates)), 2),
        "status": "candidate",
        "requires_human_review": True,
    }


async def correlate_product_cves(
    product: str,
    version: str | None,
    service: Any,
) -> dict[str, Any] | None:
    """Correlate one product/version to known CVEs and active exploits.

    Returns a single aggregated candidate finding, or ``None`` when no real
    data could be obtained (source unreachable / simulated fallback / no
    candidates) — nothing is fabricated.
    """
    from app.core.config import get_settings

    keyword = _build_keyword(product, version)
    limit = max(1, int(get_settings().cve_correlate_max_cves))
    nvd_result = await _safe_query(
        service,
        "nvd",
        {
            "keywordSearch": keyword,
            "keywordExactMatch": "false",
            "resultsPerPage": str(limit),
        },
    )
    if not _is_ok(nvd_result):
        return None
    documents: Any = nvd_result.get("data")
    candidates = _nvd_candidates(documents)
    if not candidates:
        return None

    kev_map = await _load_kev_map(service)
    for candidate in candidates:
        _apply_kev(candidate, kev_map)
    for candidate in candidates[:_MAX_ENRICH_PER_PRODUCT]:
        await _enrich_cve_report(candidate, service)

    return _build_finding(product, version, keyword, candidates, documents)


async def _load_kev_map(service: Any) -> dict[str, dict[str, Any]]:
    kev_result = await _safe_query(service, "kev", {})
    if not _is_ok(kev_result):
        return {}
    return _kev_map(kev_result.get("data"))


async def correlate_scan_report(
    report: ScanReport,
    service: Any,
) -> list[dict[str, Any]]:
    """Correlate every versioned ``Server`` banner observed in a scan.

    Technology names without a version (``page.tech``) are deliberately skipped
    — a bare product keyword is too noisy to be an honest lead.
    """
    products: list[tuple[str, str | None]] = []
    seen: set[tuple[str, str | None]] = set()
    for page in report.pages or []:
        banner = (page.headers or {}).get("server") or ""
        parsed = product_from_banner(banner)
        if parsed is None or parsed in seen:
            continue
        seen.add(parsed)
        products.append(parsed)

    findings: list[dict[str, Any]] = []
    for product, version in products:
        finding = await correlate_product_cves(product, version, service)
        if finding is not None:
            findings.append(finding)
    return findings