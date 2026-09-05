from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

from app.agents import get_archetype
from app.orchestration.state import GraphState
from app.services.source_findings import derive_findings_from_sources
from app.sources.registry import DataSourceRegistry
from app.sources.service import DataSourceError, DataSourceService, _resolve_headers
from app.sources.spec import DataSourceSpec, SourceKind, looks_like_ip


def _run(coro):
    return asyncio.run(coro)


def _registry(*specs: DataSourceSpec) -> DataSourceRegistry:
    reg = DataSourceRegistry()
    for spec in specs:
        reg.register(spec)
    return reg


# --- looks_like_ip -----------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        ("1.2.3.4", True),
        ("::1", True),
        ("2001:db8::1", True),
        ("example.com", False),
        ("not-an-ip", False),
        ("999.999.999.999", False),
    ],
)
def test_looks_like_ip(value: str, expected: bool):
    assert looks_like_ip(value) is expected


# --- header env-var resolution ------------------------------------------


def test_resolve_headers_substitutes_env_var(monkeypatch):
    monkeypatch.setenv("TEST_SECRET_KEY", "shh")
    resolved = _resolve_headers({"Key": "${TEST_SECRET_KEY}", "Accept": "application/json"})
    assert resolved == {"Key": "shh", "Accept": "application/json"}


def test_resolve_headers_drops_header_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("TEST_SECRET_KEY_UNSET", raising=False)
    resolved = _resolve_headers({"Key": "${TEST_SECRET_KEY_UNSET}", "Accept": "application/json"})
    assert resolved == {"Accept": "application/json"}
    assert "Key" not in resolved


# --- URL path templating -------------------------------------------------


@respx.mock
def test_fetch_substitutes_path_placeholder(client):
    spec = DataSourceSpec(
        name="ip-test",
        kind=SourceKind.HTTP,
        url="http://ip-test.local/json/{query}",
        query_param="query",
        params_template={"fields": "status,country"},
        fields=[],
    )
    route = respx.get("http://ip-test.local/json/8.8.8.8").mock(
        return_value=Response(200, json={"status": "success", "country": "US"})
    )
    svc = DataSourceService(_registry(spec))
    result = _run(svc.query("ip-test", {"query": "8.8.8.8"}))

    assert route.called
    # the path placeholder must not leak into the query string
    assert route.calls[0].request.url.params.get("query") is None
    assert route.calls[0].request.url.params.get("fields") == "status,country"
    assert result["status"] == "ok"


@respx.mock
def test_fetch_path_placeholder_is_url_quoted(client):
    spec = DataSourceSpec(
        name="path-test",
        kind=SourceKind.HTTP,
        url="http://path-test.local/api/{query}.json",
        query_param="query",
        fields=[],
    )
    route = respx.get("http://path-test.local/api/CVE-2024-1234.json").mock(
        return_value=Response(200, json={"ok": True})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("path-test", {"query": "CVE-2024-1234"}))
    assert route.called


def test_fetch_missing_path_param_raises(client):
    spec = DataSourceSpec(
        name="broken",
        kind=SourceKind.HTTP,
        url="http://broken.local/{query}",
        query_param="query",
    )
    svc = DataSourceService(_registry(spec))
    with pytest.raises(DataSourceError):
        _run(svc._fetch(spec, {}))

    # Through the public query() API this degrades gracefully instead of raising,
    # same as any other fetch failure (e.g. network error, 5xx).
    result = _run(svc.query("broken", {}))
    assert result["status"] == "simulated"
    assert result["reason"] == "fetch-error"


# --- headers actually sent over the wire ---------------------------------


@respx.mock
def test_fetch_sends_resolved_header(client, monkeypatch):
    monkeypatch.setenv("TEST_ABUSE_KEY", "abc123")
    spec = DataSourceSpec(
        name="abuse-test",
        kind=SourceKind.HTTP,
        url="http://abuse-test.local/check",
        headers_template={"Key": "${TEST_ABUSE_KEY}", "Accept": "application/json"},
        query_param="ipAddress",
        fields=[],
    )
    route = respx.get("http://abuse-test.local/check").mock(
        return_value=Response(200, json={"data": {"score": 0}})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("abuse-test", {"ipAddress": "1.2.3.4"}))

    assert route.called
    sent_headers = route.calls[0].request.headers
    assert sent_headers["Key"] == "abc123"
    assert sent_headers["Accept"] == "application/json"


@respx.mock
def test_fetch_omits_header_without_configured_key(client):
    spec = DataSourceSpec(
        name="abuse-test2",
        kind=SourceKind.HTTP,
        url="http://abuse-test2.local/check",
        headers_template={"Key": "${TOTALLY_UNSET_ABUSE_KEY}"},
        query_param="ipAddress",
        fields=[],
    )
    route = respx.get("http://abuse-test2.local/check").mock(
        return_value=Response(200, json={"data": {}})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("abuse-test2", {"ipAddress": "1.2.3.4"}))

    assert route.called
    assert "Key" not in route.calls[0].request.headers


# --- target_kind filtering in the generic collector -----------------------


def test_collect_sources_skips_ip_only_source_for_domain_target(client):
    ip_only = DataSourceSpec(name="ip-only", target_kind="ip", query_param="ipAddress")
    any_kind = DataSourceSpec(name="any-kind", target_kind="any", query_param="q")
    registry = _registry(ip_only, any_kind)
    service = DataSourceService(registry)

    state = GraphState(target={"name": "example.com"})
    state.set_sources_service(service)

    agent = get_archetype("hermit")
    update = _run(agent._collect_sources(state))

    queried = {r["source"] for r in update}
    assert "any-kind" in queried
    assert "ip-only" not in queried


def test_collect_sources_skips_domain_only_source_for_ip_target(client):
    domain_only = DataSourceSpec(name="domain-only", target_kind="domain", query_param="q")
    ip_only = DataSourceSpec(name="ip-only", target_kind="ip", query_param="ipAddress")
    registry = _registry(domain_only, ip_only)
    service = DataSourceService(registry)

    state = GraphState(target={"name": "1.2.3.4"})
    state.set_sources_service(service)

    agent = get_archetype("hermit")
    update = _run(agent._collect_sources(state))

    queried = {r["source"] for r in update}
    assert "ip-only" in queried
    assert "domain-only" not in queried


def test_collect_sources_skips_cve_kind_source_always(client):
    """cve_report-style sources (target_kind="cve") never join the generic sweep."""
    cve_only = DataSourceSpec(name="cve-only", target_kind="cve", query_param="query")
    any_kind = DataSourceSpec(name="any-kind", target_kind="any", query_param="q")
    registry = _registry(cve_only, any_kind)
    service = DataSourceService(registry)

    state = GraphState(target={"name": "example.com"})
    state.set_sources_service(service)

    agent = get_archetype("hermit")
    update = _run(agent._collect_sources(state))

    queried = {r["source"] for r in update}
    assert "any-kind" in queried
    assert "cve-only" not in queried


def test_collect_sources_uses_each_sources_own_query_param():
    class RecordingService:
        def __init__(self, spec: DataSourceSpec) -> None:
            self._spec = spec
            self.seen_params: dict[str, Any] | None = None

        def available_sources(self) -> list[str]:
            return [self._spec.name]

        def get_source(self, name: str) -> DataSourceSpec:
            return self._spec

        async def query(self, name: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
            self.seen_params = params
            return {"status": "simulated", "source": name, "data": {}}

    spec = DataSourceSpec(name="abuseipdb-like", target_kind="ip", query_param="ipAddress")
    service = RecordingService(spec)

    state = GraphState(target={"name": "9.9.9.9"})
    state.set_sources_service(service)

    agent = get_archetype("hermit")
    _run(agent._collect_sources(state))

    assert service.seen_params == {"ipAddress": "9.9.9.9"}


# --- real manifest sanity checks ------------------------------------------


def test_real_sources_manifest_loads_all_expected_sources():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    expected = {
        "cve",
        "osint",
        "nvd",
        "cve_report",
        "crtsh",
        "abuseipdb",
        "urlscan",
        "ip_api",
        "kev",
    }
    assert expected <= set(reg.available_sources())


@pytest.mark.parametrize(
    "name,expected_target_kind",
    [
        ("nvd", "domain"),
        ("cve_report", "cve"),
        ("crtsh", "domain"),
        ("abuseipdb", "ip"),
        ("urlscan", "domain"),
        ("ip_api", "ip"),
        ("kev", "any"),
    ],
)
def test_real_source_declares_expected_target_kind(name: str, expected_target_kind: str):
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    assert reg.get_source(name).target_kind == expected_target_kind


def test_ip_api_and_cve_report_use_path_templated_urls():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    assert "{query}" in reg.get_source("ip_api").url
    assert "{query}" in reg.get_source("cve_report").url


def test_abuseipdb_and_nvd_reference_env_var_headers():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    assert reg.get_source("abuseipdb").headers_template["Key"] == "${ABUSEIPDB_API_KEY}"
    assert reg.get_source("nvd").headers_template["apiKey"] == "${NVD_API_KEY}"


def test_kev_is_declared_as_full_feed_collected_manually():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    kev = reg.get_source("kev")
    assert kev.kind is SourceKind.HTTP
    assert kev.skip_sweep is True  # CISA catalog is queried only on demand (correlation)
    assert kev.ttl == 86400
    assert "vulnerabilities" in kev.fields


# --- source-result findings (evidence-grounded extractors) -------------------


def _source_result(name: str, data: dict, status: str = "ok") -> dict:
    return {
        "status": status,
        "source": name,
        "data": data,
        "fetched_at": "2026-01-01T00:00:00+00:00",
    }


def _derived(source: str, data: dict) -> list[dict]:
    return derive_findings_from_sources("example.com", [_source_result(source, data)])


def test_urlscan_extractor_flags_malicious_verdicts():
    data = {
        "total": 2,
        "results": [
            {
                "task": {"url": "https://example.com/page"},
                "verdicts": {"overall": {"malicious": True}},
            },
            {
                "page": {"url": "https://example.com/other"},
                "verdicts": {"overall": {"malicious": False}},
            },
        ],
    }
    findings = _derived("urlscan", data)
    assert len(findings) == 1
    assert findings[0]["title"].startswith("2 avaliação(ões)")
    assert findings[0]["severity"] == "low"
    assert "1 avaliação(ões) foi(ram) marcada(s) como maliciosa(s)" in findings[0]["description"]
    assert findings[0]["status"] == "candidate"
    assert findings[0]["requires_human_review"] is True


def test_urlscan_extractor_clean_verdicts_is_info():
    data = {"total": 1, "results": [{"task": {"url": "https://example.com/"}}]}
    findings = _derived("urlscan", data)
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"


def test_urlscan_extractor_skips_empty_results():
    assert _derived("urlscan", {"total": 0, "results": []}) == []


def test_ip_api_extractor_flags_proxy_and_hosting():
    findings = _derived(
        "ip_api",
        {"proxy": True, "hosting": True, "isp": "OVH", "org": "OVH SAS"},
    )
    assert len(findings) == 1
    assert "proxy/data center" in findings[0]["title"]
    assert findings[0]["severity"] == "info"
    assert "proxy=True" in findings[0]["evidence"]
    assert "hosting=True" in findings[0]["evidence"]
    assert findings[0]["requires_human_review"] is True


def test_ip_api_extractor_skips_residential_ip():
    assert _derived("ip_api", {"proxy": False, "hosting": False}) == []


def test_extractors_ignore_simulated_results():
    results = [
        _source_result(
            "urlscan",
            {"results": [{"task": {"url": "https://x/"}}]},
            status="simulated",
        )
    ]
    assert derive_findings_from_sources("example.com", results) == []
