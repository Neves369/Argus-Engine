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
    assert {"nvd", "hackertarget", "crtsh"} <= set(reg.available_sources())
    assert reg.has_source("hackertarget")
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
def test_duplicate_cache_rows_do_not_break_read_and_write_dedupes(client):
    """Linhas duplicadas (source,key) não podem quebrar a leitura, e a escrita
    substitui as antigas em vez de acumular (correção de self-heal)."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.db.models.external_data_cache import ExternalDataCache
    from app.db.session import async_session_factory
    from app.sources.service import _default_key

    route = respx.get("https://data.test.local/query").mock(
        return_value=Response(200, json={"id": "dup", "score": 5})
    )
    svc = DataSourceService(_registry(HTTP_SOURCE))
    params = {"q": "dup-key-unique-case2"}
    key = _default_key(HTTP_SOURCE, params)

    async def _seed():
        now = datetime.now(UTC)
        async with async_session_factory() as session:
            session.add_all(
                [
                    ExternalDataCache(
                        source="http-test",
                        key=key,
                        data={"id": "old", "score": 1},
                        fetched_at=now - timedelta(minutes=5),
                    ),
                    ExternalDataCache(
                        source="http-test",
                        key=key,
                        data={"id": "new", "score": 9},
                        fetched_at=now - timedelta(minutes=1),
                    ),
                ]
            )
            await session.commit()

    async def _count() -> int:
        async with async_session_factory() as session:
            rows = (
                await session.execute(
                    select(ExternalDataCache).where(
                        ExternalDataCache.source == "http-test",
                        ExternalDataCache.key == key,
                    )
                )
            ).scalars().all()
            return len(list(rows))

    asyncio.run(_seed())

    result = _run(svc.query("http-test", params))
    assert result["status"] == "cache"
    assert result["data"] == {"id": "new", "score": 9}
    assert route.called == 0

    # Força refetch (TTL zerado): a escrita substitui as duplicatas por uma só.
    force = DataSourceService(_registry(HTTP_SOURCE.model_copy(update={"ttl": 0})))
    result = _run(force.query("http-test", params))
    assert result["status"] == "ok"
    assert route.called == 1
    assert asyncio.run(_count()) == 1


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
    assert "hackertarget" in names
    assert "nvd" in names


@respx.mock
def test_query_source_api(client):
    respx.get("https://api.hackertarget.com/hostsearch/").mock(
        return_value=Response(200, text="www.example.com,1.2.3.4\napi.example.com,5.6.7.8\n")
    )
    resp = client.post(
        "/api/v1/sources/hackertarget/query", json={"params": {"q": "example.com"}}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "www.example.com" in body["data"]["response"]


@respx.mock
def test_query_source_api_unknown_source(client):
    resp = client.post("/api/v1/sources/nope/query", json={"params": {}})
    assert resp.status_code == 404


def test_query_source_api_scope_denied(client):
    resp = client.post(
        "/api/v1/sources/hackertarget/query", json={"params": {}, "target": "evil.example.org"}
    )
    assert resp.status_code == 403


@respx.mock
def test_query_source_api_scope_allowed(client):
    respx.get("https://api.hackertarget.com/hostsearch/").mock(
        return_value=Response(500, text="down")
    )
    resp = client.post(
        "/api/v1/sources/hackertarget/query", json={"params": {}, "target": "example.com"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "simulated"
