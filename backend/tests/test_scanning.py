from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.agents import get_archetype
from app.core.security import activate_kill_switch, deactivate_kill_switch
from app.orchestration.state import GraphState
from app.scanning.client import ScanError, ScanHTTPClient
from app.scanning.robots import RobotsRules
from app.scanning.service import ScanBlockedError, ScanReport, ScanService, build_scan_service
from app.scanning.spec import TargetPage
from app.services.scan_findings import derive_findings_from_scan


def _run(coro):
    return asyncio.run(coro)


class _NoopClient:
    """Records calls; used where the scan must never issue a request."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def get_page(self, url: str) -> TargetPage:
        self.calls.append(url)
        raise AssertionError("no request should be issued")


class _FakeScanService:
    def __init__(self, report: ScanReport | None = None, error: Exception | None = None) -> None:
        self._report = report
        self._error = error
        self.calls = 0

    async def scan(self, target: dict) -> ScanReport:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._report


def _page(**overrides) -> TargetPage:
    defaults = {
        "url": "http://example.com/",
        "status_code": 200,
        "headers": {"content-type": "text/html"},
        "body": "<html><body>ok</body></html>",
    }
    defaults.update(overrides)
    return TargetPage(**defaults)


# ---------------------------------------------------------------------------
# Controles obrigatórios: escopo, kill-switch, robots, rate limit, timeout
# ---------------------------------------------------------------------------


def test_scope_gate_blocks_scan_before_any_request():
    client = _NoopClient()
    service = ScanService(client=client, respect_robots=False)
    with pytest.raises(ScanBlockedError):
        _run(service.scan({"name": "evil.org", "url": "http://evil.org/"}))
    assert client.calls == []


def test_scope_gate_blocks_empty_target():
    service = ScanService(client=_NoopClient(), respect_robots=False)
    with pytest.raises(ScanBlockedError):
        _run(service.scan({}))
    with pytest.raises(ScanBlockedError):
        _run(service.scan({"name": ""}))


def test_kill_switch_blocks_scan():
    client = _NoopClient()
    service = ScanService(client=client, respect_robots=False)
    activate_kill_switch()
    try:
        with pytest.raises(ScanBlockedError):
            _run(service.scan({"name": "example.com", "url": "http://example.com/"}))
    finally:
        deactivate_kill_switch()
    assert client.calls == []


@respx.mock
def test_robots_txt_respected():
    respx.get("http://example.com/robots.txt").mock(
        return_value=httpx.Response(200, text="User-agent: *\nDisallow: /admin/\n")
    )
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<html><body>"
                '<a href="/admin/">hidden</a>'
                '<a href="/contact">contact</a>'
                "</body></html>"
            ),
        )
    )
    respx.get("http://example.com/contact").mock(
        return_value=httpx.Response(200, text="<html><body>contact</body></html>")
    )

    service = ScanService(client=ScanHTTPClient(rate_limit=0), respect_robots=True)
    report = _run(service.scan({"name": "example.com", "url": "http://example.com/"}))

    assert report.robots_respected is True
    assert report.urls_skipped_by_robots == 1
    urls = [p.url for p in report.pages]
    assert urls == ["http://example.com/", "http://example.com/contact"]
    assert not any("admin" in u for u in urls)


def test_robots_prefix_rules():
    rules = RobotsRules.parse(
        "User-agent: *\nDisallow: /admin/\nAllow: /admin/public/",
        user_agent="ArgusEngine/0.1 (authorized scanning)",
    )
    assert rules.is_allowed("/") is True
    assert rules.is_allowed("/contact") is True
    assert rules.is_allowed("/admin/") is False
    assert rules.is_allowed("/admin/users") is False
    assert rules.is_allowed("/admin/public/x") is True

    blocked = RobotsRules.parse("User-agent: *\nDisallow: /\n", user_agent="crawl")
    assert blocked.is_allowed("/anything") is False
    assert RobotsRules.parse("", user_agent="x").is_allowed("/") is True


def test_rate_limit_enforced_per_target():
    client = ScanHTTPClient(rate_limit=1.0)
    with respx.mock:
        respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="ok"))
        assert _run(client.get_page("http://example.com/")).status_code == 200
    with pytest.raises(ScanError, match="Rate limit"):
        _run(client.get_page("http://example.com/"))


def test_request_failure_wrapped_as_scan_error():
    with respx.mock:
        respx.get("http://example.com/").mock(side_effect=httpx.ReadTimeout("boom"))
        with pytest.raises(ScanError):
            _run(ScanHTTPClient().get_page("http://example.com/"))


# ---------------------------------------------------------------------------
# Crawl: mesma origem, teto de páginas, fallback de esquema
# ---------------------------------------------------------------------------


@respx.mock
def test_crawl_stays_on_same_host_and_respects_max_pages():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text=(
                "<html><body>"
                '<a href="/a">a</a>'
                '<a href="/b">b</a>'
                '<a href="http://external.test/elsewhere">out</a>'
                "</body></html>"
            ),
        )
    )
    respx.get("http://example.com/a").mock(return_value=httpx.Response(200, text="<p>a</p>"))

    service = ScanService(client=ScanHTTPClient(rate_limit=0), respect_robots=False, max_pages=2)
    report = _run(service.scan({"name": "example.com", "url": "http://example.com/"}))

    urls = [p.url for p in report.pages]
    assert urls == ["http://example.com/", "http://example.com/a"]
    assert not any("external.test" in u for u in urls)


@respx.mock
def test_derived_https_falls_back_to_http():
    respx.get("https://example.com/").mock(side_effect=httpx.ConnectError("tls down"))
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="<html>ok</html>"))

    service = ScanService(client=ScanHTTPClient(rate_limit=0), respect_robots=False)
    report = _run(service.scan({"name": "example.com"}))

    assert [p.url for p in report.pages] == ["http://example.com/"]


@respx.mock
def test_unreachable_target_yields_no_findings_and_note():
    respx.get("http://example.com/").mock(side_effect=httpx.ConnectError("down"))

    service = ScanService(client=ScanHTTPClient(rate_limit=0), respect_robots=False)
    report = _run(service.scan({"name": "example.com", "url": "http://example.com/"}))

    assert report.pages == []
    assert report.note
    assert derive_findings_from_scan(report) == []


# ---------------------------------------------------------------------------
# Detecção passiva e findings evidence-grounded
# ---------------------------------------------------------------------------


@respx.mock
def test_passive_detections_produce_grounded_findings():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            headers={
                "Server": "Apache/2.4.49 (Ubuntu)",
                "Set-Cookie": "session=abc; Path=/",
                "Access-Control-Allow-Origin": "*",
            },
            text=(
                "<html><head>"
                '<meta name="generator" content="WordPress 6.0">'
                "</head><body>"
                '<form method="post" action="/login">'
                '<input type="text" name="user">'
                '<input type="password" name="pass">'
                "</form><p>wp-content lives here</p>"
                "</body></html>"
            ),
        )
    )

    service = ScanService(client=ScanHTTPClient(rate_limit=0), respect_robots=False)
    report = _run(service.scan({"name": "example.com", "url": "http://example.com/"}))

    html_page = report.pages[0]
    assert "WordPress" in html_page.tech
    assert len(html_page.forms) == 1
    assert html_page.forms[0].action == "/login"

    findings = derive_findings_from_scan(report)
    titles = {f["title"] for f in findings}
    assert "Servidor divulga versão exata no header de resposta" in titles
    assert "Headers de segurança ausentes na resposta" in titles
    assert "Cookies de sessão sem flags de proteção" in titles
    assert "Formulários com entrada de dados encontrados" in titles
    assert "CORS permissivo (Access-Control-Allow-Origin: *)" in titles
    for finding in findings:
        assert finding["status"] == "candidate"
        assert finding["requires_human_review"] is True
        assert finding["evidence"]
        assert finding["cves"] == []


@respx.mock
def test_clean_page_yields_no_findings():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            headers={
                "Server": "nginx",
                "Content-Security-Policy": "default-src 'self'",
                "Strict-Transport-Security": "max-age=31536000",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Permissions-Policy": "camera=()",
                "Set-Cookie": "sid=1; Secure; HttpOnly; SameSite=Strict",
            },
            text="<html><body>hello</body></html>",
        )
    )
    report = _run(
        ScanService(client=ScanHTTPClient(rate_limit=0), respect_robots=False).scan(
            {"name": "example.com", "url": "http://example.com/"}
        )
    )
    assert derive_findings_from_scan(report) == []


def test_server_banner_requires_digit_no_finding():
    page = _page(headers={"server": "nginx"})
    findings = derive_findings_from_scan(ScanReport(target="example.com", pages=[page]))
    titles = {f["title"] for f in findings}
    assert "Servidor divulga versão exata no header de resposta" not in titles


def test_server_banner_with_version_yields_server_finding():
    page = _page(headers={"server": "Apache/2.4.49 (Ubuntu)"})
    findings = derive_findings_from_scan(ScanReport(target="example.com", pages=[page]))
    assert any("Servidor divulga versão exata" in f["title"] for f in findings)


# ---------------------------------------------------------------------------
# Integração com o Eremita
# ---------------------------------------------------------------------------


def test_hermit_without_scan_service_skips_scan():
    state = GraphState(target={"name": "example.com"})
    update = _run(get_archetype("hermit").run(state))
    entry = update["history"][-1]
    assert entry["scanned"] is False
    assert "scan" not in update


def test_hermit_with_scan_service_records_scan_and_findings():
    page = _page(headers={"server": "Apache/2.4.49 (Ubuntu)"}, body="<html>x</html>")
    report = ScanReport(target="example.com", pages=[page])
    fake = _FakeScanService(report=report)
    state = GraphState(target={"name": "example.com"})
    state.set_scan_service(fake)

    update = _run(get_archetype("hermit").run(state))

    assert fake.calls == 1
    assert update["scan"] == [report.to_dict()]
    assert any("Servidor divulga versão exata" in f["title"] for f in update["findings"])
    entry = update["history"][-1]
    assert entry["scanned"] is True
    assert entry["pages_observed"] == 1


def test_hermit_survives_blocked_scan_without_fabricating_findings():
    fake = _FakeScanService(error=ScanBlockedError("kill switch"))
    state = GraphState(target={"name": "example.com"})
    state.set_scan_service(fake)

    update = _run(get_archetype("hermit").run(state))

    assert update["findings"] == []
    assert "scan" not in update
    assert update["history"][-1]["scanned"] is False


# ---------------------------------------------------------------------------
# Factory e caminho completo via API
# ---------------------------------------------------------------------------


def test_build_scan_service_from_settings():
    service = build_scan_service()
    assert isinstance(service, ScanService)


def test_api_run_with_scan_service_persists_scan(client, monkeypatch):
    report = ScanReport(
        target="example.com",
        pages=[_page(headers={"server": "Apache/2.4.49 (Ubuntu)"}, body="<html>x</html>")],
    )
    fake = _FakeScanService(report=report)
    monkeypatch.setattr("app.api.v1.runs.build_scan_service", lambda: fake)

    res = client.post(
        "/api/v1/runs",
        json={"target": {"name": "example.com", "url": "http://example.com/"}},
    )
    assert res.status_code == 201
    run_id = res.json()["id"]

    run = client.get(f"/api/v1/runs/{run_id}").json()
    assert run["status"] == "completed"
    assert run["result"]["scan"]
    assert any("Servidor divulga versão exata" in f["title"] for f in run["result"]["findings"])
    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    assert any("Servidor divulga" in f["title"] for f in findings)
    assert fake.calls >= 1