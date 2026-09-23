from __future__ import annotations

import asyncio
import json

import httpx
import respx

from app.probing.engine import ProbeEngine
from app.scanning.client import ScanHTTPClient
from app.scanning.service import ScanReport, ScanService
from app.scanning.spec import TargetPage
from app.services.scan_findings import derive_findings_from_scan

TARGET = "example.com"
BASE = "http://example.com/"

_ROOT_HTML = "<html><head><title>root</title></head><body>ok</body></html>"

_INTROSPECTION_OPEN = json.dumps(
    {"data": {"__schema": {"queryType": {"name": "Query"}, "mutationType": None}}}
)
_INTROSPECTION_BLOCKED = json.dumps(
    {"errors": [{"message": "GraphQL introspection is not allowed"}]}
)


def _run(coro):
    return asyncio.run(coro)


def _service(**kwargs):
    defaults = {
        "client": ScanHTTPClient(rate_limit=0),
        "respect_robots": False,
        "max_pages": 3,
        "graphql_enabled": True,
    }
    defaults.update(kwargs)
    return ScanService(**defaults)


def _surface(findings):
    return [f for f in findings if "endpoint(s) GraphQL detectado(s)" in (f["title"] or "")]


@respx.mock
def test_graphql_discovered_by_canonical_path_and_surface_finding():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "graphql").mock(
        return_value=httpx.Response(200, text="Must provide query string")
    )
    for path in ("graphql/", "gql", "api/graphql"):
        respx.get(BASE + path).mock(return_value=httpx.Response(404))

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert report.graphql_endpoints == [
        {
            "url": BASE + "graphql",
            "method": "POST",
            "session": "anon",
            "detected_by": "path",
        }
    ]

    findings = derive_findings_from_scan(report)
    surface = _surface(findings)
    assert len(surface) == 1
    assert surface[0]["category"] == "Aplicação / superfície de API"
    assert surface[0]["status"] == "candidate"
    assert surface[0]["extras"]["endpoint_count"] == 1
    assert "graphql" in surface[0]["evidence"]

    as_dict = report.to_dict()
    assert len(as_dict["graphql_endpoints"]) == 1


@respx.mock
def test_graphql_discovered_by_html_reference():
    root = '<html><body><script src="/data/graphql"></script>ok</body></html>'
    respx.get(BASE).mock(return_value=httpx.Response(200, text=root))
    for path in ("graphql", "graphql/", "gql", "api/graphql"):
        respx.get(BASE + path).mock(return_value=httpx.Response(404))

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert len(report.graphql_endpoints) == 1
    endpoint = report.graphql_endpoints[0]
    assert endpoint["url"] == BASE + "data/graphql"
    assert endpoint["detected_by"] == "reference"


@respx.mock
def test_graphql_fail_closed_when_no_endpoint():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    for path in ("graphql", "graphql/", "gql", "api/graphql"):
        respx.get(BASE + path).mock(return_value=httpx.Response(404))

    report = _run(_service().scan({"name": TARGET, "url": BASE}))

    assert report.graphql_endpoints == []
    assert "graphql: nenhum endpoint detectado" in (report.note or "")
    assert _surface(derive_findings_from_scan(report)) == []


@respx.mock
def test_graphql_disabled_skips_discovery():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "graphql").mock(
        return_value=httpx.Response(200, text="Must provide query string")
    )

    report = _run(_service(graphql_enabled=False).scan({"name": TARGET, "url": BASE}))

    assert report.graphql_endpoints == []
    assert report.api_spec is None


@respx.mock
def test_graphql_respects_robots_disallow():
    respx.get(BASE).mock(return_value=httpx.Response(200, text=_ROOT_HTML))
    respx.get(BASE + "robots.txt").mock(
        return_value=httpx.Response(
            200,
            text="User-agent: *\nDisallow: /graphql\nAllow: /\n",
        )
    )
    respx.get(BASE + "graphql").mock(
        return_value=httpx.Response(200, text="Must provide query string")
    )
    for path in ("graphql/", "gql", "api/graphql"):
        respx.get(BASE + path).mock(return_value=httpx.Response(404))

    report = _run(_service(respect_robots=True).scan({"name": TARGET, "url": BASE}))

    assert report.graphql_endpoints == []
    assert report.urls_skipped_by_robots >= 1


def test_graphql_direct_discovery_labels_session():
    client = ScanHTTPClient(rate_limit=0)

    async def _run_report():
        report = ScanReport(target=TARGET)
        with respx.mock:
            respx.get(BASE + "graphql").mock(
                return_value=httpx.Response(200, text="Must provide query string")
            )
            for path in ("graphql/", "gql", "api/graphql"):
                respx.get(BASE + path).mock(return_value=httpx.Response(404))
            await _service()._discover_graphql(report, BASE, client=client, session="admin")
        return report

    report = _run(_run_report())

    assert report.graphql_endpoints == [
        {
            "url": BASE + "graphql",
            "method": "POST",
            "session": "admin",
            "detected_by": "path",
        }
    ]


# ---------------------------------------------------------------------------
# Probe de introspecção (M8-P2) — política graphql_introspection_p1
# ---------------------------------------------------------------------------


def _page(url: str, body: str, status_code: int = 200) -> TargetPage:
    return TargetPage(url=url, status_code=status_code, headers={}, body=body)


def _graphql_report(*endpoints: dict) -> ScanReport:
    return ScanReport(
        target=TARGET,
        pages=[_page(BASE, _ROOT_HTML)],
        graphql_endpoints=list(endpoints),
    )


class _GraphQLClient:
    user_agent = "ArgusTest"

    def __init__(self, response: TargetPage) -> None:
        self.response = response
        self.posts: list[tuple[str, dict]] = []

    async def post_json(self, url: str, payload: dict) -> TargetPage:
        self.posts.append((url, payload))
        return self.response


def _run_probe(report: ScanReport, client: object) -> tuple[list[dict], list[dict]]:
    engine = ProbeEngine(client=client, respect_robots=False, max_probes=10)
    return _run(
        engine.run(
            report=report,
            findings=[],
            target={"name": TARGET},
            probe_classes=["graphql_introspection_p1"],
        )
    )


def _endpoint(url: str, session: str = "anon") -> dict:
    return {"url": url, "method": "POST", "session": session, "detected_by": "path"}


def test_graphql_introspection_positive_when_schema_exposed():
    client = _GraphQLClient(_page(BASE + "graphql", _INTROSPECTION_OPEN))
    report = _graphql_report(_endpoint(BASE + "graphql"))

    behavior, records = _run_probe(report, client)

    assert len(behavior) == 1
    finding = behavior[0]
    assert finding["category"] == "Comportamento / Introspecção GraphQL aberta"
    assert finding["status"] == "candidate"
    assert finding["extras"]["rule_ids"] == ["graphql_introspection_p1"]
    assert records[0]["positive"] is True
    assert records[0]["session"] == "anon"


def test_graphql_introspection_sends_versioned_json_query():
    client = _GraphQLClient(_page(BASE + "graphql", _INTROSPECTION_OPEN))
    report = _graphql_report(_endpoint(BASE + "graphql"))

    _run_probe(report, client)

    assert len(client.posts) == 1
    url, payload = client.posts[0]
    assert url == BASE + "graphql"
    assert "query" in payload
    assert "__schema" in payload["query"]


def test_graphql_introspection_negative_when_blocked():
    client = _GraphQLClient(_page(BASE + "graphql", _INTROSPECTION_BLOCKED))
    report = _graphql_report(_endpoint(BASE + "graphql"))

    behavior, records = _run_probe(report, client)

    assert behavior == []
    assert records[0]["positive"] is False
    assert records[0]["fp_matched"] is True


def test_graphql_introspection_negative_on_403():
    client = _GraphQLClient(
        _page(BASE + "graphql", '{"error": "forbidden"}', status_code=403)
    )
    report = _graphql_report(_endpoint(BASE + "graphql"))

    behavior, records = _run_probe(report, client)

    assert behavior == []
    assert records[0]["positive"] is False
    assert records[0]["fp_matched"] is True


def test_graphql_introspection_not_in_default_p0_allowlist():
    engine = ProbeEngine(respect_robots=False)
    resolved = engine.resolve_classes(None)
    assert "graphql_introspection_p1" not in resolved
    assert "graphql_introspection_p1" in engine.resolve_classes(["graphql_introspection_p1"])

