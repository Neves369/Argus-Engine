from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Any

import pytest
import respx
from httpx import Response

from app.agents import get_archetype
from app.orchestration.state import GraphState
from app.services.source_findings import derive_findings_from_sources
from app.sources.registry import DataSourceRegistry
from app.sources.service import (
    DataSourceError,
    DataSourceService,
    _resolve_basic_auth,
    _resolve_headers,
)
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


# --- env-var placeholders in query params (key-as-query-param sources) -------


@respx.mock
def test_fetch_substitutes_env_var_in_params(client, monkeypatch):
    monkeypatch.setenv("SHODAN_TEST_KEY", "secret123")
    spec = DataSourceSpec(
        name="shodan-like",
        kind=SourceKind.HTTP,
        url="http://shodan-like.local/host/{query}",
        params_template={"key": "${SHODAN_TEST_KEY}"},
        query_param="query",
        fields=[],
    )
    route = respx.get("http://shodan-like.local/host/8.8.8.8").mock(
        return_value=Response(200, json={"ports": []})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("shodan-like", {"query": "8.8.8.8"}))
    assert route.called
    assert route.calls[0].request.url.params.get("key") == "secret123"


@respx.mock
def test_fetch_omits_unset_env_param(client, monkeypatch):
    monkeypatch.delenv("SHODAN_TEST_KEY_UNSET", raising=False)
    spec = DataSourceSpec(
        name="shodan-like2",
        kind=SourceKind.HTTP,
        url="http://shodan-like2.local/host/{query}",
        params_template={"key": "${SHODAN_TEST_KEY_UNSET}", "minify": "true"},
        query_param="query",
        fields=[],
    )
    route = respx.get("http://shodan-like2.local/host/1.2.3.4").mock(
        return_value=Response(200, json={"ports": []})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("shodan-like2", {"query": "1.2.3.4"}))
    assert route.called
    assert "key" not in route.calls[0].request.url.params
    assert route.calls[0].request.url.params.get("minify") == "true"


# --- HTTP Basic auth (auth_basic) -------------------------------------------


def test_resolve_basic_auth_builds_header(monkeypatch):
    monkeypatch.setenv("API_TEST_ID", "acme")
    monkeypatch.setenv("API_TEST_SECRET", "swordfish")
    expected = "Basic " + base64.b64encode(b"acme:swordfish").decode()
    assert _resolve_basic_auth(["${API_TEST_ID}", "${API_TEST_SECRET}"]) == expected


def test_resolve_basic_auth_returns_none_when_credential_unset(monkeypatch):
    monkeypatch.delenv("API_TEST_ID_UNSET", raising=False)
    monkeypatch.setenv("API_TEST_SECRET_SET", "x")
    assert _resolve_basic_auth(["${API_TEST_ID_UNSET}", "${API_TEST_SECRET_SET}"]) is None


def test_resolve_basic_auth_requires_two_templates():
    assert _resolve_basic_auth(["${ONLY_ONE}"]) is None
    assert _resolve_basic_auth(["literal", "${B}"]) is None
    assert _resolve_basic_auth([]) is None


@respx.mock
def test_fetch_sends_basic_auth_header(client, monkeypatch):
    monkeypatch.setenv("CENSYS_TEST_ID", "acme")
    monkeypatch.setenv("CENSYS_TEST_SECRET", "swordfish")
    spec = DataSourceSpec(
        name="censys-like",
        kind=SourceKind.HTTP,
        url="http://censys-like.local/hosts/{query}",
        auth_basic=["${CENSYS_TEST_ID}", "${CENSYS_TEST_SECRET}"],
        query_param="query",
        fields=[],
    )
    route = respx.get("http://censys-like.local/hosts/8.8.8.8").mock(
        return_value=Response(200, json={"result": {}})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("censys-like", {"query": "8.8.8.8"}))
    assert route.called
    expected = "Basic " + base64.b64encode(b"acme:swordfish").decode()
    assert route.calls[0].request.headers["Authorization"] == expected


@respx.mock
def test_fetch_omits_basic_auth_without_configured_credentials(client):
    spec = DataSourceSpec(
        name="censys-like2",
        kind=SourceKind.HTTP,
        url="http://censys-like2.local/hosts/{query}",
        auth_basic=["${CENSYS_TEST_ID_UNSET}", "${CENSYS_TEST_SECRET_UNSET}"],
        query_param="query",
        fields=[],
    )
    route = respx.get("http://censys-like2.local/hosts/8.8.8.8").mock(
        return_value=Response(200, json={"result": {}})
    )
    svc = DataSourceService(_registry(spec))
    _run(svc.query("censys-like2", {"query": "8.8.8.8"}))
    assert route.called
    assert "Authorization" not in route.calls[0].request.headers


# --- redirect following (RDAP bootstrap) -------------------------------------


@respx.mock
def test_fetch_follows_redirects_when_enabled(client):
    spec = DataSourceSpec(
        name="rdap-like",
        kind=SourceKind.HTTP,
        url="http://rdap-like.local/domain/{query}",
        query_param="query",
        follow_redirects=True,
        fields=[],
    )
    initial = respx.get("http://rdap-like.local/domain/example.com").mock(
        return_value=Response(
            302, headers={"Location": "http://registry-like.local/domain/example.com"}
        )
    )
    final = respx.get("http://registry-like.local/domain/example.com").mock(
        return_value=Response(200, json={"objectClassName": "domain", "ldhName": "example.com"})
    )
    svc = DataSourceService(_registry(spec))
    result = _run(svc.query("rdap-like", {"query": "example.com"}))
    assert initial.called
    assert final.called  # the bootstrap redirect was followed
    assert result["status"] == "ok"


@respx.mock
def test_fetch_does_not_follow_redirects_by_default(client):
    spec = DataSourceSpec(
        name="rdap-like2",
        kind=SourceKind.HTTP,
        url="http://rdap-like2.local/domain/{query}",
        query_param="query",
        fields=[],
    )
    initial = respx.get("http://rdap-like2.local/domain/example.com").mock(
        return_value=Response(
            302, headers={"Location": "http://registry-like2.local/domain/example.com"}
        )
    )
    final = respx.get("http://registry-like2.local/domain/example.com").mock(
        return_value=Response(200, json={"objectClassName": "domain"})
    )
    svc = DataSourceService(_registry(spec))
    result = _run(svc.query("rdap-like2", {"query": "example.com"}))
    assert initial.called
    assert not final.called
    assert result["status"] != "ok" or "domain" not in str(result["data"])


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
        "nvd",
        "cve_report",
        "crtsh",
        "abuseipdb",
        "urlscan",
        "ip_api",
        "hackertarget",
        "kev",
        "internetdb",
        "shodan",
        "censys",
        "rdap",
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
        ("hackertarget", "domain"),
        ("kev", "any"),
        ("internetdb", "ip"),
        ("shodan", "ip"),
        ("censys", "ip"),
        ("rdap", "domain"),
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


def test_new_ip_sources_use_path_templated_urls():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    for name in ("internetdb", "shodan", "censys", "rdap"):
        assert "{query}" in reg.get_source(name).url


def test_abuseipdb_and_nvd_reference_env_var_headers():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    assert reg.get_source("abuseipdb").headers_template["Key"] == "${ABUSEIPDB_API_KEY}"
    assert reg.get_source("nvd").headers_template["apiKey"] == "${NVD_API_KEY}"


def test_shodan_censys_and_rdap_declare_secret_and_redirect_styles():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    shodan = reg.get_source("shodan")
    assert shodan.params_template["key"] == "${SHODAN_API_KEY}"
    assert reg.get_source("censys").auth_basic == ["${CENSYS_API_ID}", "${CENSYS_API_SECRET}"]
    assert reg.get_source("rdap").follow_redirects is True


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


def test_hackertarget_extractor_parses_hostname_lines():
    data = {
        "response": (
            "www.example.com,1.2.3.4\n"
            "api.example.com,5.6.7.8\n"
            "\n"
            "WWW.EXAMPLE.COM,1.2.3.4\n"
        )
    }
    findings = _derived("hackertarget", data)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["title"].startswith("2 host(s) de forward DNS")
    assert "www.example.com" in finding["evidence"]
    assert "api.example.com" in finding["evidence"]
    assert finding["severity"] == "info"
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True


def test_hackertarget_extractor_ignores_target_itself():
    data = {"response": "example.com,1.2.3.4\nwww.example.com,5.6.7.8\n"}
    findings = _derived("hackertarget", data)
    assert len(findings) == 1
    assert "example.com,1.2.3.4" not in findings[0]["evidence"]


def test_hackertarget_extractor_skips_empty_or_unknown_shapes():
    assert _derived("hackertarget", {"response": ""}) == []
    assert _derived("hackertarget", {"response": "\n\n"}) == []
    assert _derived("hackertarget", {"response": "no-ip-here"}) == []


def test_hackertarget_extractor_ignores_simulated_results():
    results = [
        _source_result(
            "hackertarget",
            {"response": "www.example.com,1.2.3.4\n"},
            status="simulated",
        )
    ]
    assert derive_findings_from_sources("example.com", results) == []


def test_extractors_ignore_simulated_results():
    results = [
        _source_result(
            "urlscan",
            {"results": [{"task": {"url": "https://x/"}}]},
            status="simulated",
        )
    ]
    assert derive_findings_from_sources("example.com", results) == []


# --- new IP-surface extractors (Shodan/InternetDB, Censys) -------------------


def test_shodan_extractor_surfaces_ports_and_cves():
    findings = _derived(
        "shodan",
        {
            "org": "ACME Hosting",
            "asn": "AS12345",
            "ports": [80, 443, 22],
            "hostnames": ["server1.acme.com"],
            "vulns": ["CVE-2020-0001", "CVE-2021-0002"],
        },
    )
    assert len(findings) == 1
    finding = findings[0]
    assert finding["title"].startswith("3 porta(s) exposta(s)")
    assert finding["severity"] == "low"  # CVEs listed -> low lead
    assert finding["cves"] == ["CVE-2020-0001", "CVE-2021-0002"]
    assert "org: ACME Hosting" in finding["evidence"]
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True


def test_internetdb_extractor_info_when_only_ports():
    findings = _derived(
        "internetdb",
        {
            "ip": "1.2.3.4",
            "ports": [443],
            "cpes": ["cpe:/a:nginx:nginx"],
            "hostnames": ["www.example.com"],
            "vulns": [],
            "tags": ["cloud"],
        },
    )
    assert len(findings) == 1
    assert findings[0]["severity"] == "info"  # no CVEs -> informational surface
    assert findings[0]["cves"] == []
    assert "porta(s)=[443]" in findings[0]["evidence"]


def test_shodan_extractor_skips_empty_shape():
    assert _derived("internetdb", {"ip": "1.2.3.4", "hostnames": []}) == []
    assert _derived("shodan", {}) == []


def test_censys_extractor_lists_services():
    data = {
        "code": 200,
        "status": "OK",
        "result": {
            "ip": "1.2.3.4",
            "services": [
                {"service_name": "HTTP", "port": 80, "transport_protocol": "TCP"},
                {"service_name": None, "port": 2222},
            ],
        },
    }
    findings = _derived("censys", data)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["severity"] == "info"
    assert "HTTP @ 80/TCP" in finding["evidence"]
    assert "unknown @ 2222" in finding["evidence"]
    assert finding["status"] == "candidate"


def test_censys_extractor_accepts_flat_payload_too():
    findings = _derived("censys", {"services": [{"service_name": "SSH", "port": 22}]})
    assert len(findings) == 1
    assert "SSH @ 22" in findings[0]["evidence"]


def test_censys_extractor_skips_no_services():
    assert _derived("censys", {"ip": "1.2.3.4", "services": []}) == []
    assert _derived("censys", {}) == []


def test_new_extractors_ignore_simulated_results():
    results = [
        _source_result(
            "internetdb", {"ports": [80], "vulns": ["CVE-2020-0001"]}, status="simulated"
        ),
        _source_result(
            "censys", {"services": [{"service_name": "HTTP", "port": 80}]}, status="simulated"
        ),
        _source_result("rdap", {"entities": [{"roles": ["registrar"]}]}, status="simulated"),
    ]
    assert derive_findings_from_sources("example.com", results) == []


# --- RDAP passive-WHOIS extractor --------------------------------------------


def test_rdap_extractor_surfaces_registrar_nameservers_and_dates():
    data = {
        "ldhName": "example.com",
        "entities": [
            {
                "objectClassName": "entity",
                "roles": ["registrar"],
                "vcardArray": [
                    "vcard",
                    [["fn", {}, "text", "Charleston Road Registry Inc"]],
                ],
            }
        ],
        "nameservers": [
            {"ldhName": ["ns1.example.com", "ns2.example.com"]},
            {"ldhName": "ns3.example.com"},
        ],
        "events": [
            {"eventAction": "registration", "eventDate": "2020-01-01T00:00:00Z"},
            {"eventAction": "expiration", "eventDate": "2026-01-01T00:00:00Z"},
        ],
        "status": ["client transfer prohibited"],
    }
    findings = _derived("rdap", data)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["category"] == "Gestão de domínio"
    assert finding["severity"] == "info"
    assert "registrar=Charleston Road Registry Inc" in finding["title"]
    assert "3 nameserver(s)" in finding["title"]
    assert "expira em 2026-01-01T00:00:00Z" in finding["title"]
    assert "ns1.example.com" in finding["evidence"]
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True


def test_rdap_extractor_skips_empty_shape():
    assert _derived("rdap", {}) == []
    assert _derived("rdap", {"ldhName": "example.com", "status": []}) == []


def test_rdap_extractor_ignores_entities_without_registrar_role():
    data = {"entities": [{"objectClassName": "entity", "roles": ["abuse"], "vcardArray": []}]}
    assert _derived("rdap", data) == []
