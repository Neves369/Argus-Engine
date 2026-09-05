from __future__ import annotations

import asyncio
from pathlib import Path

from app.agents import get_archetype
from app.orchestration.state import GraphState
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage
from app.services.cve_correlate import (
    correlate_product_cves,
    correlate_scan_report,
    product_from_banner,
)
from app.sources.registry import DataSourceRegistry
from app.sources.service import DataSourceError

_SOURCES_PATH = Path(__file__).resolve().parents[1] / "sources.json"


def _run(coro):
    return asyncio.run(coro)


def _page(**overrides) -> TargetPage:
    defaults = {
        "url": "http://example.com/",
        "status_code": 200,
        "headers": {"content-type": "text/html"},
        "body": "<html><body>ok</body></html>",
    }
    defaults.update(overrides)
    return TargetPage(**defaults)


class _FakeScanService:
    def __init__(self, report: ScanReport | None = None) -> None:
        self._report = report

    async def scan(self, target: dict) -> ScanReport:
        return self._report


class _CorrelateSourcesService:
    """Real-spec sources service; canned, real-shaped NVD/KEV/cve.report data.

    Uses the real ``sources.json`` manifest for specs (so ``_collect_sources``
    target-kind/skip_sweep filtering behaves exactly like production), but
    returns deterministic payloads instead of making network calls.
    """

    def __init__(self, *, nvd_error: bool = False, empty_nvd: bool = False) -> None:
        self._registry = DataSourceRegistry(_SOURCES_PATH)
        self._nvd_error = nvd_error
        self._empty_nvd = empty_nvd
        self.calls: list[tuple[str, dict]] = []

    def available_sources(self) -> list[str]:
        return self._registry.available_sources()

    def get_source(self, name: str):
        return self._registry.get_source(name)

    async def query(self, name: str, params: dict | None = None) -> dict:
        params = params or {}
        self.calls.append((name, params))
        stamp = "2026-01-01T00:00:00+00:00"
        if self._nvd_error and name == "nvd":
            raise DataSourceError("nvd rate limited")
        if name == "nvd":
            keyword = str(params.get("keywordSearch", ""))
            if "apache" not in keyword:
                return {"status": "simulated", "source": "nvd", "data": {}, "fetched_at": stamp}
            if self._empty_nvd:
                return {
                    "status": "ok",
                    "source": "nvd",
                    "data": {"totalResults": 0, "vulnerabilities": []},
                    "fetched_at": stamp,
                }
            return {
                "status": "ok",
                "source": "nvd",
                "data": _NVD_DATA,
                "fetched_at": stamp,
            }
        if name == "kev":
            return {"status": "ok", "source": "kev", "data": _KEV_DATA, "fetched_at": stamp}
        if name == "cve_report":
            cve_id = params.get("query")
            if cve_id == "CVE-2021-41773":
                return {
                    "status": "ok",
                    "source": "cve_report",
                    "data": _CVE_REPORT_DATA,
                    "fetched_at": stamp,
                }
            return {
                "status": "ok",
                "source": "cve_report",
                "data": {"cve_id": cve_id},
                "fetched_at": stamp,
            }
        if name == "crtsh":
            return {
                "status": "ok",
                "source": "crtsh",
                "data": {"response": []},
                "fetched_at": stamp,
            }
        return {"status": "simulated", "source": name, "data": {}, "fetched_at": stamp}


_NVD_DATA = {
    "totalResults": 12,
    "vulnerabilities": [
        {
            "cve": {
                "id": "CVE-2021-41773",
                "vulnStatus": "Analyzed",
                "sourceIdentifier": "cve@mitre.org",
                "published": "2021-10-04T22:15:00.000",
                "lastModified": "2021-10-05T13:00:00.000",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": "A flaw was found in a change made to path normalization "
                        "in Apache HTTP Server 2.4.49.",
                    }
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {
                            "source": "nvd@nist.gov",
                            "type": "Primary",
                            "cvssData": {
                                "version": "3.1",
                                "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
                                "baseScore": 9.8,
                                "baseSeverity": "CRITICAL",
                            },
                        }
                    ]
                },
                "references": [
                    {"url": "https://httpd.apache.org/security/vulnerabilities_24.html"}
                ],
                "cisaExploitAdd": "2021-10-21",
                "cisaVulnerabilityName": "Apache HTTP Server Path Traversal and RCE",
            }
        },
        {
            "cve": {
                "id": "CVE-2021-42013",
                "vulnStatus": "Analyzed",
                "sourceIdentifier": "cve@mitre.org",
                "published": "2021-10-04T22:15:00.000",
                "lastModified": "2021-10-05T13:00:00.000",
                "descriptions": [
                    {
                        "lang": "en",
                        "value": "An incomplete fix for CVE-2021-41773 in Apache HTTP Server "
                        "2.4.50.",
                    }
                ],
                "metrics": {
                    "cvssMetricV31": [
                        {
                            "cvssData": {
                                "version": "3.1",
                                "vectorString": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:N",
                                "baseScore": 9.8,
                                "baseSeverity": "CRITICAL",
                            }
                        }
                    ]
                },
                "references": [],
            }
        },
    ],
}

_KEV_DATA = {
    "title": "CISA Catalog of Known Exploited Vulnerabilities",
    "catalogVersion": "2026.01.01",
    "dateReleased": "2026-01-01T00:00:00.000Z",
    "count": 1,
    "vulnerabilities": [
        {
            "cveID": "CVE-2021-41773",
            "vendorProject": "Apache",
            "product": "HTTP Server",
            "vulnerabilityName": "Apache HTTP Server Path Traversal and RCE",
            "dateAdded": "2021-10-21",
            "shortDescription": "Apache HTTP Server 2.4.49 includes a fix for a "
            "path traversal issue.",
            "requiredAction": "Apply updates per vendor instructions.",
            "dueDate": "2021-11-11",
            "knownRansomwareCampaignUse": "Unknown",
            "notes": "",
        }
    ],
}

_CVE_REPORT_DATA = {
    "cve_id": "CVE-2021-41773",
    "references": [
        "https://httpd.apache.org/security/vulnerabilities_24.html",
        {"url": "https://nvd.nist.gov/vuln/detail/CVE-2021-41773"},
    ],
    "enrichments": {
        "KEV": {"cveID": "CVE-2021-41773", "dateAdded": "2021-10-21"},
        "EPSS": {"score": 0.97, "percentile": 0.99},
    },
}


# --- banner parsing ----------------------------------------------------------


def test_product_from_banner_parses_product_and_version():
    assert product_from_banner("Apache/2.4.49 (Ubuntu)") == ("apache http server", "2.4.49")
    assert product_from_banner("nginx/1.18.0") == ("nginx", "1.18.0")


def test_product_from_banner_requires_version():
    assert product_from_banner("nginx") is None
    assert product_from_banner("Server: Apache") is None
    assert product_from_banner("") is None


# --- core correlation --------------------------------------------------------


def test_correlate_product_cves_with_real_shapes():
    service = _CorrelateSourcesService()
    finding = _run(correlate_product_cves("apache http server", "2.4.49", service))

    assert finding is not None
    assert finding["cves"] == ["CVE-2021-41773", "CVE-2021-42013"]
    assert finding["severity"] == "critical"
    assert finding["cvss_score"] == 9.8
    assert finding["cvss_vector"].startswith("CVSS:3.1")
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True
    assert finding["confidence"] < 0.6
    assert "apache http server 2.4.49" in finding["evidence"]

    assert len(finding["known_exploits"]) == 1
    assert "CVE-2021-41773" in finding["known_exploits"][0]
    assert "CVE-2021-42013" not in "".join(finding["known_exploits"])

    nvd_calls = [p for name, p in service.calls if name == "nvd"]
    assert any(
        p.get("keywordSearch") == "apache http server 2.4.49"
        and p.get("resultsPerPage") == "5"
        for p in nvd_calls
    )


def test_correlate_returns_none_when_nvd_simulated():
    # "ghostproduct" is not routed to the canned NVD payload -> simulated.
    service = _CorrelateSourcesService()
    finding = _run(correlate_product_cves("ghostproduct", "1.0", service))
    assert finding is None


def test_correlate_returns_none_when_nvd_empty():
    service = _CorrelateSourcesService(empty_nvd=True)
    finding = _run(correlate_product_cves("apache http server", "2.4.49", service))
    assert finding is None


def test_correlate_survives_source_rate_limit():
    service = _CorrelateSourcesService(nvd_error=True)
    finding = _run(correlate_product_cves("apache http server", "2.4.49", service))
    assert finding is None


# --- scan report correlation -------------------------------------------------


def test_correlate_scan_report_collects_and_dedupes_banners():
    service = _CorrelateSourcesService()
    report = ScanReport(
        target="example.com",
        pages=[
            _page(headers={"server": "Apache/2.4.49 (Ubuntu)"}),
            _page(url="http://example.com/2", headers={"server": "Apache/2.4.49 (Ubuntu)"}),
            _page(url="http://example.com/3", headers={"server": "nginx"}),  # no version -> skipped
        ],
    )
    findings = _run(correlate_scan_report(report, service))
    assert len(findings) == 1
    assert findings[0]["cves"] == ["CVE-2021-41773", "CVE-2021-42013"]


def test_correlate_scan_report_without_banners_yields_nothing():
    service = _CorrelateSourcesService()
    report = ScanReport(target="example.com", pages=[_page(headers={"server": "nginx"})])
    assert _run(correlate_scan_report(report, service)) == []


# --- HermitAgent integration -------------------------------------------------


def test_hermit_integrates_correlated_cves_into_findings():
    report = ScanReport(
        target="example.com",
        pages=[_page(headers={"server": "Apache/2.4.49 (Ubuntu)"}, body="<html>x</html>")],
    )
    state = GraphState(target={"name": "example.com"})
    state.set_scan_service(_FakeScanService(report=report))
    state.set_sources_service(_CorrelateSourcesService())

    update = _run(get_archetype("hermit").run(state))

    titles = {f["title"] for f in update["findings"]}
    assert any("CVE(s) correlacionado(s)" in t for t in titles)
    correlated = [f for f in update["findings"] if "CVE(s) correlacionado(s)" in f["title"]]
    assert correlated[0]["known_exploits"]
    assert update["history"][-1]["cve_correlations"] == 1


def test_hermit_correlation_is_best_effort():
    report = ScanReport(
        target="example.com",
        pages=[_page(headers={"server": "Apache/2.4.49 (Ubuntu)"})],
    )
    state = GraphState(target={"name": "example.com"})
    state.set_sources_service(_BoomSourcesService())
    agent = get_archetype("hermit")

    assert _run(agent._correlate_cves(state, report)) == []


class _BoomSourcesService:
    def available_sources(self) -> list[str]:
        return []

    def get_source(self, name: str):
        raise AssertionError("should not be consulted")

    async def query(self, name: str, params: dict | None = None) -> dict:
        raise RuntimeError("unexpected correlation failure")