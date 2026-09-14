from __future__ import annotations

import asyncio

import httpx
import respx

from app.agents.builtin import _depth_scan_max_pages
from app.core.config import budget_for_depth, get_settings
from app.orchestration.director import Director
from app.orchestration.state import GraphState
from app.scanning.client import ScanHTTPClient
from app.scanning.service import ScanReport, ScanService


def _run(coro):
    return asyncio.run(coro)


class _FakeScanService:
    def __init__(self, report: ScanReport | None = None) -> None:
        self._report = report or ScanReport(target="example.com", pages=[])

    async def scan(self, target: dict, *, max_pages: int | None = None) -> ScanReport:
        return self._report


# ---------------------------------------------------------------------------
# Estado e time
# ---------------------------------------------------------------------------


def test_state_depth_defaults_to_quick():
    assert GraphState().depth == "quick"


def test_resolve_team_deep_adds_chariot():
    team = Director._resolve_team(GraphState(target={"name": "example.com"}, depth="deep"))
    assert set(team) == {"fool", "hermit", "magician", "chariot"}


def test_resolve_team_quick_excludes_chariot():
    team = Director._resolve_team(GraphState(target={"name": "example.com"}))
    assert team == ["fool", "hermit", "magician"]


# ---------------------------------------------------------------------------
# Orçamento e crawl por profundidade
# ---------------------------------------------------------------------------


def test_budget_for_depth_distinct():
    quick_tokens, quick_cost = budget_for_depth("quick")
    deep_tokens, deep_cost = budget_for_depth("deep")
    assert deep_tokens > quick_tokens
    assert deep_cost > quick_cost


def test_depth_scan_max_pages():
    settings = get_settings()
    assert _depth_scan_max_pages(GraphState(depth="deep")) == settings.deep_scan_max_pages
    assert _depth_scan_max_pages(GraphState(depth="quick")) is None


@respx.mock
def test_scan_max_pages_override_limits_crawl():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text='<a href="/a">a</a><a href="/b">b</a><a href="/c">c</a>',
        )
    )
    respx.get("http://example.com/a").mock(return_value=httpx.Response(200, text="a"))
    respx.get("http://example.com/b").mock(return_value=httpx.Response(200, text="b"))
    respx.get("http://example.com/c").mock(return_value=httpx.Response(200, text="c"))

    service = ScanService(
        client=ScanHTTPClient(rate_limit=0), respect_robots=False, max_pages=10
    )
    report = _run(
        service.scan(
            {"name": "example.com", "url": "http://example.com/"}, max_pages=2
        )
    )

    assert [p.url for p in report.pages] == ["http://example.com/", "http://example.com/a"]


# ---------------------------------------------------------------------------
# Imperador registra a decisão de depth no estado/auditoria
# ---------------------------------------------------------------------------


def test_emperor_records_deep_in_history():
    final = _run(Director().run(GraphState(target={"name": "example.com"}, depth="deep")))

    assert final.depth == "deep"
    emperor_entries = [e for e in final.history if e["agent"] == "emperor"]
    assert emperor_entries
    assert all(e["depth"] == "deep" for e in emperor_entries)


def test_quick_run_has_no_chariot_entries():
    final = _run(Director().run(GraphState(target={"name": "example.com"})))

    assert final.depth == "quick"
    assert all(e["agent"] != "chariot" for e in final.history)


# ---------------------------------------------------------------------------
# API: depth no run (quick vs deep, validação)
# ---------------------------------------------------------------------------


def _patch_runtime(monkeypatch, scan_service):
    monkeypatch.setattr("app.api.v1.runs.build_scan_service", lambda: scan_service)
    monkeypatch.setattr("app.api.v1.runs.build_verification_service", lambda: None)
    monkeypatch.setattr("app.api.v1.runs.build_tool_executor", lambda: None)


def test_api_run_deep_includes_chariot_and_records_depth(client, monkeypatch):
    _patch_runtime(monkeypatch, _FakeScanService())

    res = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com", "url": "http://example.com/"}, "depth": "deep"},
    )

    assert res.status_code == 201
    result = res.json()["result"]
    assert result["depth"] == "deep"
    agents = [e["agent"] for e in result["history"]]
    assert "chariot" in agents
    assert any(e.get("depth") == "deep" for e in result["history"] if e["agent"] == "emperor")


def test_api_run_quick_excludes_chariot(client, monkeypatch):
    _patch_runtime(monkeypatch, _FakeScanService())

    res = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com", "url": "http://example.com/"}},
    )

    assert res.status_code == 201
    result = res.json()["result"]
    assert result["depth"] == "quick"
    assert all(e["agent"] != "chariot" for e in result["history"])


def test_api_run_rejects_invalid_depth(client):
    res = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com", "url": "http://example.com/"}, "depth": "medium"},
    )
    assert res.status_code == 422
