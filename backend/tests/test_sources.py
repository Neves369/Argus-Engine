from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import respx
from httpx import Response

from app.sources.registry import DataSourceRegistry
from app.sources.service import DataSourceError, DataSourceService
from app.sources.spec import DataSourceSpec, SourceKind


def _run(coro):
    return asyncio.run(coro)


def _registry(*specs: DataSourceSpec) -> DataSourceRegistry:
    reg = DataSourceRegistry()
    for spec in specs:
        reg.register(spec)
    return reg


HTTP_SOURCE = DataSourceSpec(
    name="http-test",
    description="test",
    kind=SourceKind.HTTP,
    url="https://data.test.local/query",
    method="GET",
    timeout=5.0,
    rate_limit=0.0,
    ttl=3600,
    fields=["id", "score"],
)


CVE_SOURCE = DataSourceSpec(
    name="cve-test",
    description="test",
    kind=SourceKind.CVE,
    url="https://cve.test.local/api/cve",
    method="GET",
    timeout=5.0,
    rate_limit=0.0,
    ttl=3600,
    fields=["cve_id", "cvss"],
)


def test_registry_loads_manifest():
    path = Path(__file__).resolve().parents[1] / "sources.json"
    reg = DataSourceRegistry(path)
    assert {"cve", "osint"} <= set(reg.available_sources())
    assert reg.has_source("cve")
    assert not reg.has_source("nope")


def test_minimize_dict_fields_only():
    src = DataSourceSpec(name="x", fields=["a", "b"])
    from app.sources.service import _minimize

    out = _minimize(src, {"a": 1, "b": 2, "secret": 3})
    assert out == {"a": 1, "b": 2}


def test_minimize_list_fields_only():
    src = DataSourceSpec(name="x", fields=["id"])
    from app.sources.service import _minimize

    out = _minimize(src, [{"id": 1, "pii": "x"}, {"id": 2, "pii": "y"}])
    assert out == {"items": [{"id": 1}, {"id": 2}]}


def test_fallback_when_source_not_configured():
    svc = DataSourceService(_registry())
    result = _run(svc.query("missing", {"q": 1}))
    assert result["status"] == "simulated"
    assert result["reason"] == "source-not-configured"
    assert "requested" in result["data"]


@respx.mock
def test_fetch_normalizes_and_minimizes(client):
    route = respx.get("https://data.test.local/query").mock(
        return_value=Response(200, json={"id": "abc", "score": 98, "secret": "nope"})
    )
    svc = DataSourceService(_registry(HTTP_SOURCE))
    result = _run(svc.query("http-test", {"q": "x"}))
    assert route.called
    assert result["status"] == "ok"
    assert result["data"] == {"id": "abc", "score": 98}
    assert "secret" not in result["data"]


@respx.mock
def test_cache_hit_avoids_second_fetch(client):
    route = respx.get("https://data.test.local/query").mock(
        return_value=Response(200, json={"id": "cache-me", "score": 7})
    )
    svc = DataSourceService(_registry(HTTP_SOURCE))
    params = {"q": "unique-cache-key-1"}
    first = _run(svc.query("http-test", params))
    assert first["status"] == "ok"
    assert route.called == 1

    second = _run(svc.query("http-test", params))
    assert second["status"] == "cache"
    assert route.called == 1
    assert second["data"] == {"id": "cache-me", "score": 7}


@respx.mock
def test_cache_expired_refetches(client):
    expired = HTTP_SOURCE.model_copy(update={"ttl": 0, "name": "http-expired"})
    route = respx.get("https://data.test.local/query").mock(
        return_value=Response(200, json={"id": "e", "score": 1})
    )
    svc = DataSourceService(_registry(expired))
    params = {"q": "expired-key"}
    _run(svc.query("http-expired", params))
    second = _run(svc.query("http-expired", params))
    assert second["status"] == "ok"
    assert route.call_count == 2


@respx.mock
def test_cve_cache_uses_cve_cache_table(client):
    route = respx.get("https://cve.test.local/api/cve").mock(
        return_value=Response(200, json={"cve_id": "CVE-2000-0001", "cvss": 9.8, "x": 1})
    )
    svc = DataSourceService(_registry(CVE_SOURCE))
    params = {"id": "CVE-2000-0001"}
    first = _run(svc.query("cve-test", params))
    assert first["status"] == "ok"
    assert first["data"] == {"cve_id": "CVE-2000-0001", "cvss": 9.8}
    assert "x" not in first["data"]
    assert route.called == 1

    second = _run(svc.query("cve-test", params))
    assert second["status"] == "cache"
    assert route.called == 1


@respx.mock
def test_fetch_error_returns_simulated(client):
    respx.get("https://data.test.local/query").mock(return_value=Response(503, text="down"))
    svc = DataSourceService(_registry(HTTP_SOURCE))
    result = _run(svc.query("http-test", {"q": "err-key-unique"}))
    assert result["status"] == "simulated"
    assert result["reason"] == "fetch-error"


@respx.mock
def test_rate_limit_raises():
    limited = HTTP_SOURCE.model_copy(update={"name": "http-limited", "rate_limit": 1.0})
    respx.get("https://data.test.local/query").mock(
        return_value=Response(200, json={"id": "r", "score": 1})
    )
    svc = DataSourceService(_registry(limited))
    _run(svc.query("http-limited", {}))
    with pytest.raises(DataSourceError):
        _run(svc.query("http-limited", {}))


@respx.mock
def test_rate_limit_burst_allows_back_to_back_calls():
    burst = HTTP_SOURCE.model_copy(
        update={"name": "http-burst", "rate_limit": 1.0, "rate_burst": 3}
    )
    route = respx.get("https://data.test.local/query").mock(
        return_value=Response(200, json={"id": "b", "score": 1})
    )
    svc = DataSourceService(_registry(burst))
    # Distinct params -> distinct cache keys -> each call fetches over HTTP.
    for i in range(3):
        result = _run(svc.query("http-burst", {"q": f"burst-{i}"}))
        assert result["status"] == "ok"
    with pytest.raises(DataSourceError):
        _run(svc.query("http-burst", {"q": "burst-3"}))
    assert route.call_count == 3


def test_list_sources_api(client):
    resp = client.get("/api/v1/sources")
    assert resp.status_code == 200
    names = {s["name"] for s in resp.json()}
    assert "cve" in names
    assert "osint" in names


@respx.mock
def test_query_source_api(client):
    respx.get("https://cve.example.local/api/cve").mock(
        return_value=Response(200, json={"cve_id": "CVE-2024-9999", "cvss": 9.8, "extra": 1})
    )
    resp = client.post(
        "/api/v1/sources/cve/query", json={"params": {"id": "CVE-2024-9999"}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["data"] == {"cve_id": "CVE-2024-9999", "cvss": 9.8}


@respx.mock
def test_query_source_api_unknown_source(client):
    resp = client.post("/api/v1/sources/nope/query", json={"params": {}})
    assert resp.status_code == 404


def test_query_source_api_scope_denied(client):
    resp = client.post(
        "/api/v1/sources/cve/query", json={"params": {}, "target": "evil.example.org"}
    )
    assert resp.status_code == 403


@respx.mock
def test_query_source_api_scope_allowed(client):
    respx.get("https://cve.example.local/api/cve").mock(
        return_value=Response(500, text="down")
    )
    resp = client.post(
        "/api/v1/sources/cve/query", json={"params": {}, "target": "example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "simulated"
