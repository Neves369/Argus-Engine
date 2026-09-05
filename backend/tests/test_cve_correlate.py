from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

import pytest
import respx
from httpx import Response
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

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
from app.sources.service import DataSourceError, DataSourceService
from app.sources.spec import DataSourceSpec, SourceKind

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


# --- integration with the real DataSourceService (respx) ---------------------
#
# These specs mirror `sources.json` but are built in memory so the recorded
# HTTP interaction is fully deterministic and isolated from the shared test
# database's external-source cache table.

_NVD_SPEC = DataSourceSpec(
    name="nvd",
    description="test",
    kind=SourceKind.CVE,
    url="https://services.nvd.nist.gov/rest/json/cves/2.0",
    method="GET",
    headers_template={"apiKey": "${NVD_API_KEY}"},
    timeout=5.0,
    rate_limit=0.0,
    ttl=21600,
    fields=["totalResults", "vulnerabilities"],
    query_param="keywordSearch",
    target_kind="domain",
)

_KEV_SPEC = DataSourceSpec(
    name="kev",
    description="test",
    kind=SourceKind.HTTP,
    url="https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json",
    method="GET",
    timeout=5.0,
    rate_limit=0.0,
    ttl=86400,
    fields=["vulnerabilities"],
    query_param="q",
    target_kind="any",
    skip_sweep=True,
)

_CVE_REPORT_SPEC = DataSourceSpec(
    name="cve_report",
    description="test",
    kind=SourceKind.CVE,
    url="https://cve.report/api/cve/{query}.json",
    method="GET",
    timeout=5.0,
    rate_limit=0.0,
    ttl=86400,
    fields=[],
    query_param="query",
    target_kind="cve",
)


def _real_service() -> DataSourceService:
    registry = DataSourceRegistry()
    registry.register(_NVD_SPEC)
    registry.register(_KEV_SPEC)
    registry.register(_CVE_REPORT_SPEC)
    return DataSourceService(registry)


@pytest.fixture
def isolated_cache_db(monkeypatch):
    """Point the sources service at a throwaway cache DB.

    ``DataSourceService`` reads/writes ``cve_cache``/``external_data_cache``
    through the app-wide ``async_session_factory`` — pointing it at the shared
    ``test.db`` would (a) require the alembic migration to have run first and
    (b) pollute tables other tests assert on (``test_new_models_crud`` expects
    exactly one ``external_data_cache`` row). A temp DB with just the two cache
    tables keeps the respx integration tests hermetic.
    """
    from app.db.base import Base
    from app.db.models.cve_cache import CveCache
    from app.db.models.external_data_cache import ExternalDataCache

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async def _create() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[CveCache.__table__, ExternalDataCache.__table__],
            )

    asyncio.run(_create())
    monkeypatch.setattr("app.sources.service.async_session_factory", factory)
    yield
    asyncio.run(engine.dispose())
    os.unlink(path)


@respx.mock
def test_real_service_correlate_end_to_end(isolated_cache_db):
    nvd = respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=Response(200, json=_NVD_DATA)
    )
    kev = respx.get(
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    ).mock(return_value=Response(200, json=_KEV_DATA))
    cve_report = respx.get("https://cve.report/api/cve/CVE-2021-41773.json").mock(
        return_value=Response(200, json=_CVE_REPORT_DATA)
    )
    respx.get("https://cve.report/api/cve/CVE-2021-42013.json").mock(
        return_value=Response(200, json={"cve_id": "CVE-2021-42013"})
    )

    finding = _run(correlate_product_cves("apache http server", "2.4.49", _real_service()))

    assert nvd.called
    request = nvd.calls[0].request
    assert request.url.params.get("keywordSearch") == "apache http server 2.4.49"
    assert request.url.params.get("resultsPerPage") == "5"
    # NVD CVE API 2.0 rejects keywordExactMatch with any value (404) — it must
    # not be sent (verified live; documented in ADR-0008).
    assert request.url.params.get("keywordExactMatch") is None

    assert kev.called
    assert cve_report.called

    assert finding is not None
    assert finding["cves"] == ["CVE-2021-41773", "CVE-2021-42013"]
    assert finding["severity"] == "critical"
    assert finding["cvss_score"] == 9.8
    assert any("CVE-2021-41773" in e for e in finding["known_exploits"])
    assert any("nvd.nist.gov" in r for r in finding["references"])
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True


@respx.mock
def test_real_service_reuses_http_cache_between_calls(isolated_cache_db):
    route = respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=Response(200, json=_NVD_DATA)
    )
    respx.get(
        "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    ).mock(return_value=Response(200, json=_KEV_DATA))
    respx.get("https://cve.report/api/cve/CVE-2021-41773.json").mock(
        return_value=Response(200, json=_CVE_REPORT_DATA)
    )

    service = _real_service()
    params = {
        "keywordSearch": "apache http server 2.4.49",
        "resultsPerPage": "5",
    }
    first = _run(service.query("nvd", params))
    second = _run(service.query("nvd", params))

    assert first["status"] == "ok"
    assert second["status"] == "cache"
    assert route.call_count == 1
    assert second["data"]["vulnerabilities"][0]["cve"]["id"] == "CVE-2021-41773"


@respx.mock
def test_real_service_nvd_unreachable_yields_no_finding(isolated_cache_db):
    respx.get("https://services.nvd.nist.gov/rest/json/cves/2.0").mock(
        return_value=Response(503, text="down")
    )
    service = _real_service()

    finding = _run(correlate_product_cves("apache http server", "2.4.49", service))

    assert finding is None

    direct = _run(service.query("nvd", {"keywordSearch": "x"}))
    assert direct["status"] == "simulated"
    assert direct["reason"] == "fetch-error"