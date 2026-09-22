from __future__ import annotations

import asyncio
import json

import httpx
import respx

from app.scanning.client import ScanHTTPClient
from app.scanning.service import ScanReport, ScanService
from app.services.scan_findings import derive_findings_from_scan

TARGET = "example.com"
BASE = "http://example.com/"

_ROOT_HTML = "<html><head><title>root</title></head><body>ok</body></html>"


def _run(coro):
    return asyncio.run(coro)


def _service(**kwargs):
    defaults = {
        "client": ScanHTTPClient(rate_limit=0),
        "respect_robots": False,
        "max_pages": 3,
        "openapi_enabled": True,
    }
    defaults.update(kwargs)
    return ScanService(**defaults)


def _spec(paths, servers=None):
    spec = {
        "openapi": "3.0.0",
        "info": {"title": "t", "version": "1.0.0"},
        "paths": paths,
    }
    if servers is not None:
        spec["servers"] = servers
    return json.dumps(spec)


def _surface(findings):
    return [f for f in findings if "endpoint(s) de API mapeados" in (f["title"] or "")]


@respx.mock
def test_openapi_discovered_and_surface_finding_derived():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "openapi.json").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "application/json"},
            text=_spec(
                {
                    "/api/users": {
                        "get": {
                            "parameters": [{"name": "id", "in": "path", "required": True}]
                        },
                        "post": {},
                    },
                    "/api/health": {"get": {}},
                }
            ),
        )
    )
    respx.get(BASE + "swagger.json").mock(return_value=httpx.Response(404))
    respx.get(BASE + "openapi.yaml").mock(return_value=httpx.Response(404))

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert report.api_spec is not None
    assert report.api_spec["url"] == BASE + "openapi.json"
    assert len(report.api_spec["sha256"]) == 64
    assert report.api_spec["session"] == "anon"
    assert report.api_endpoints == [
        {
            "method": "GET",
            "path": "/api/users",
            "params": ["id"],
            "session": "anon",
            "url": BASE + "api/users",
        },
        {
            "method": "POST",
            "path": "/api/users",
            "params": [],
            "session": "anon",
            "url": BASE + "api/users",
        },
        {
            "method": "GET",
            "path": "/api/health",
            "params": [],
            "session": "anon",
            "url": BASE + "api/health",
        },
    ]

    findings = derive_findings_from_scan(report)
    surface = _surface(findings)
    assert len(surface) == 1
    assert surface[0]["category"] == "Aplicação / superfície de API"
    assert surface[0]["status"] == "candidate"
    assert surface[0]["extras"]["endpoint_count"] == 3
    assert surface[0]["extras"]["distinct_paths"] == 2
    assert surface[0]["extras"]["spec_sha256"] == report.api_spec["sha256"]
    assert surface[0]["extras"]["sessions"] == ["anon"]
    assert "GET /api/users" in surface[0]["evidence"]

    as_dict = report.to_dict()
    assert as_dict["api_spec"]["session"] == "anon"
    assert len(as_dict["api_endpoints"]) == 3


@respx.mock
def test_openapi_falls_back_to_next_candidate_on_missing():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "openapi.json").mock(return_value=httpx.Response(404))
    respx.get(BASE + "swagger.json").mock(
        return_value=httpx.Response(
            200,
            text=_spec({"/api/ping": {"get": {}}}),
        )
    )

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert report.api_spec is not None
    assert report.api_spec["url"] == BASE + "swagger.json"
    assert len(report.api_endpoints) == 1
    assert report.api_endpoints[0]["path"] == "/api/ping"
    assert report.note is None


@respx.mock
def test_openapi_fail_closed_on_invalid_spec():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "openapi.json").mock(return_value=httpx.Response(200, text="not a spec"))
    respx.get(BASE + "swagger.json").mock(return_value=httpx.Response(404))
    respx.get(BASE + "openapi.yaml").mock(return_value=httpx.Response(404))

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert report.api_spec is None
    assert report.api_endpoints == []
    assert "inválida" in (report.note or "")
    assert _surface(derive_findings_from_scan(report)) == []


@respx.mock
def test_openapi_out_of_host_paths_are_filtered():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "openapi.json").mock(
        return_value=httpx.Response(
            200,
            text=_spec(
                {
                    "/api/users": {"get": {}},
                    "https://other.example.com/api/x": {"get": {}},
                },
                servers=[{"url": "https://other.example.com"}],
            ),
        )
    )
    respx.get(BASE + "swagger.json").mock(return_value=httpx.Response(404))
    respx.get(BASE + "openapi.yaml").mock(return_value=httpx.Response(404))

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert [e["path"] for e in report.api_endpoints] == ["/api/users"]
    assert report.api_spec is not None


@respx.mock
def test_openapi_disabled_skips_discovery():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "openapi.json").mock(return_value=httpx.Response(200, text=_spec({})))

    report = _run(_service(openapi_enabled=False).scan({"name": TARGET, "url": BASE}))

    assert report.api_spec is None
    assert report.api_endpoints == []


@respx.mock
def test_openapi_respects_robots_disallow():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /openapi.json\nDisallow: /swagger.json\nAllow: /\n",
        )
    )
    respx.get(BASE + "openapi.json").mock(return_value=httpx.Response(200, text=_spec({})))
    respx.get(BASE + "openapi.yaml").mock(return_value=httpx.Response(404))

    report = _run(
        _service(respect_robots=True).scan({"name": TARGET, "url": BASE})
    )

    assert report.urls_skipped_by_robots >= 2
    assert report.api_spec is None
    assert report.api_endpoints == []


def test_openapi_direct_discovery_labels_session_for_multi_profile():
    client = ScanHTTPClient(rate_limit=0)

    async def _run_report():
        report = ScanReport(target=TARGET)
        with respx.mock:
            respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
            respx.get(BASE + "robots.txt").mock(return_value=httpx.Response(200, text=""))
            respx.get(BASE + "openapi.json").mock(
                return_value=httpx.Response(200, text=_spec({"/api/admin": {"get": {}}}))
            )
            await _service()._discover_openapi(
                report, BASE, client=client, session="admin"
            )
        return report

    report = _run(_run_report())

    assert report.api_spec["session"] == "admin"
    assert report.api_endpoints == [
        {
            "method": "GET",
            "path": "/api/admin",
            "params": [],
            "session": "admin",
            "url": BASE + "api/admin",
        }
    ]