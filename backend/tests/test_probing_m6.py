from __future__ import annotations

import asyncio

import pytest
import yaml
from pydantic import ValidationError

from app.core.security import (
    activate_kill_switch,
    deactivate_kill_switch,
    is_kill_switch_active,
)
from app.db.models import Finding, Run
from app.probing.catalog import load_catalog
from app.probing.engine import ProbeEngine
from app.scanning.client import ScanError
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage
from app.services.export import finding_section, run_report, run_report_markdown
from app.services.scan_findings import derive_findings_from_scan

TARGET = "example.com"
REFLECT_URL = "http://example.com/echo.php?id=hello"
ERROR_URL = "http://example.com/login.php"


def _run(coro):
    return asyncio.run(coro)


def _stub_client(
    pages: dict[str, TargetPage],
    robots_body: str | None = None,
    post_fn=None,
) -> object:
    class _StubClient:
        user_agent = "ArgusTest"

        def __init__(self) -> None:
            self.pages = pages
            self.robots_body = robots_body or "User-agent: *\nAllow: /"
            self.post_fn = post_fn
            self.calls: list[str] = []
            self.post_calls: list[tuple[str, dict]] = []

        async def get_page(self, url: str):
            self.calls.append(url)
            page = self.pages.get(url)
            if page is None:
                raise ScanError(f"no stub for {url}")
            return page

        async def post_page(self, url: str, data: dict[str, str]):
            self.post_calls.append((url, data))
            if self.post_fn is None:
                raise ScanError(f"no post stub for {url}")
            return self.post_fn(url, data)

        async def fetch_no_rate_limit(self, url: str):
            self.calls.append(url)
            return TargetPage(
                url=url,
                status_code=200,
                headers={"content-type": "text/plain"},
                body=self.robots_body,
            )

    return _StubClient()


def _page(url: str, body: str) -> TargetPage:
    return TargetPage(url=url, status_code=200, headers={}, body=body)


def _reflect_findings(*, live_body: str) -> tuple[ScanReport, list[dict]]:
    report = ScanReport(
        target=TARGET,
        pages=[_page(REFLECT_URL, "<html><body>echo: hello</body></html>")],
    )
    return report, derive_findings_from_scan(report)


def _error_findings(*, live_body: str) -> tuple[ScanReport, list[dict]]:
    report = ScanReport(
        target=TARGET,
        pages=[_page(ERROR_URL, "<html><body>undefined variable foo</body></html>")],
    )
    return report, derive_findings_from_scan(report)


def test_catalog_loads_all_probe_policies():
    catalog = load_catalog()
    assert sorted(catalog) == [
        "authn_p3",
        "csrf_p2",
        "injection_p1",
        "redirect_p2",
        "reflection_p0",
        "upload_p1",
        "verbose_error_p0",
    ]
    assert {p.id for p in catalog.values() if p.priority == "P0"} == {
        "reflection_p0",
        "verbose_error_p0",
    }
    assert {p.id for p in catalog.values() if p.priority == "P1"} == {
        "injection_p1",
        "upload_p1",
    }
    assert {p.id for p in catalog.values() if p.priority == "P2"} == {
        "csrf_p2",
        "redirect_p2",
    }
    assert {p.id for p in catalog.values() if p.priority == "P3"} == {"authn_p3"}
    assert all(p.default_enabled for p in catalog.values())


def test_catalog_fails_closed_on_duplicate_id(tmp_path, monkeypatch):
    import app.probing.catalog as catalog_mod

    (tmp_path / "a.yaml").write_text(_yaml("dup"))
    (tmp_path / "b.yaml").write_text(_yaml("dup"))
    monkeypatch.setattr(catalog_mod, "PROBES_PATH", tmp_path)
    catalog_mod.load_catalog.cache_clear()
    try:
        with pytest.raises(ValueError, match="Duplicate probe policy id"):
            catalog_mod.load_catalog()
    finally:
        catalog_mod.load_catalog.cache_clear()


def test_catalog_fails_closed_on_invalid_policy(tmp_path, monkeypatch):
    import app.probing.catalog as catalog_mod

    (tmp_path / "bad.yaml").write_text(
        "id: broken\nversion: 1.0.0\nname: sem prioridade\n"
    )
    monkeypatch.setattr(catalog_mod, "PROBES_PATH", tmp_path)
    catalog_mod.load_catalog.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError)):
            catalog_mod.load_catalog()
    finally:
        catalog_mod.load_catalog.cache_clear()


def test_default_probe_classes_p0_only(monkeypatch):
    names = {p.id for p in load_catalog().values() if "p0" in p.id.lower()}
    assert names == {"reflection_p0", "verbose_error_p0"}
    # O default seguro resolve "p0" para as políticas P0 habilitadas por default.
    engine = ProbeEngine(respect_robots=False)
    assert engine.resolve_classes(None) == sorted(names)


def test_reflection_reproduced_is_positive():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client({REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    assert len(behavior) == 1
    finding = behavior[0]
    assert finding["category"] == "Comportamento / Reflexão não codificada"
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True
    assert finding["extras"]["probes"][0]["positive"] is True
    assert finding["extras"]["probes"][0]["rule_id"] == "reflection_p0"


def test_reflection_no_longer_reproduced_is_not_positive():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client(
        {REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: removed</body></html>")}
    )
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    assert behavior == []
    assert len(records) == 1
    assert records[0]["positive"] is False
    assert records[0]["detail"].startswith("sinal não confirmado")


def test_verbose_error_reproduced_is_positive():
    error_body = "<html><body>Fatal error: undefined variable foo</body></html>"
    report, findings = _error_findings(live_body=error_body)
    stub = _stub_client({ERROR_URL: _page(ERROR_URL, error_body)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    assert len(behavior) == 1
    assert behavior[0]["category"] == "Comportamento / Erro verboso / info leak"
    assert records[0]["positive"] is True


def test_out_of_scope_runs_nothing():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client({REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": "evil.org"})
    )

    assert behavior == []
    assert records == []
    assert stub.calls == []


def test_kill_switch_blocks_probes():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client({REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")})
    engine = ProbeEngine(client=stub, respect_robots=False)

    activate_kill_switch()
    try:
        behavior, records = _run(
            engine.run(report=report, findings=findings, target={"name": TARGET})
        )
    finally:
        deactivate_kill_switch()

    assert not is_kill_switch_active()
    assert behavior == []
    assert records == []
    assert stub.calls == []


def test_robots_disallow_skips_probe_auditably():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client(
        {REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")},
        robots_body="User-agent: *\nDisallow: /",
    )
    engine = ProbeEngine(client=stub, respect_robots=True, max_probes=10)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    assert behavior == []
    assert len(records) == 1
    assert records[0]["skipped"] is True
    assert records[0]["skip_reason"] == "robots disallow"
    assert len([c for c in stub.calls if "echo.php" in c]) == 0


def test_max_probes_cap_is_enforced():
    url_a = "http://example.com/echo.php?id=aaa"
    url_b = "http://example.com/echo.php?id=bbb"
    report = ScanReport(
        target=TARGET,
        pages=[
            _page(url_a, "<html><body>echo: aaa</body></html>"),
            _page(url_b, "<html><body>echo: bbb</body></html>"),
        ],
    )
    findings = derive_findings_from_scan(report)
    stub = _stub_client(
        {
            url_a: _page(url_a, "<html><body>echo: aaa</body></html>"),
            url_b: _page(url_b, "<html><body>echo: bbb</body></html>"),
        }
    )
    engine = ProbeEngine(client=stub, respect_robots=False, max_probes=1)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    assert len(records) == 1
    executed = [r for r in records if not r["skipped"]]
    assert len(executed) == 1


def test_per_endpoint_cap_is_enforced():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client({REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")})
    catalog = {
        "reflection_p0": _dup_policy("reflection_p0"),
        "reflection_p0_bis": _dup_policy("reflection_p0_bis"),
    }
    engine = ProbeEngine(
        client=stub,
        respect_robots=False,
        max_per_endpoint=1,
        max_probes=10,
        catalog=catalog,
    )
    # Ambas as classes miram os mesmos leads de reflexão — a segunda tem que ser
    # pulada pelo teto por endpoint (registrado como skipped, nunca executado).
    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    assert len(behavior) == 1
    skipped = [r for r in records if r["skipped"] and r["skip_reason"] == "per-endpoint cap"]
    assert len(skipped) == 1


def test_export_report_includes_behavior_section():
    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client({REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")})

    behavior, records = _run(
        ProbeEngine(client=stub, respect_robots=False).run(
            report=report, findings=findings, target={"name": TARGET}
        )
    )
    finding = Finding(
        title=behavior[0]["title"],
        severity="low",
        category=behavior[0]["category"],
        affected="example.com",
        confidence=0.6,
        status="candidate",
        requires_human_review=True,
        description=behavior[0]["description"],
        remediation=behavior[0]["remediation"],
        meta={"evidence": behavior[0]["evidence"], "extras": behavior[0]["extras"]},
    )
    run = Run(
        id=1,
        status="completed",
        result={"target": {"name": TARGET}},
    )

    assert finding_section(finding) == "comportamento"
    report_json = run_report(run, [finding])
    assert report_json["summary"]["executive"]["comportamento"] == 1
    assert report_json["summary"]["by_section"]["comportamento"] == 1
    assert "## Comportamento" in run_report_markdown(run, [finding])


def test_chariot_wires_the_probe_engine():
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client(
        {REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")}
    )
    engine = ProbeEngine(client=stub, respect_robots=False)
    state = GraphState(target={"name": TARGET}, depth="deep")
    state.set_probe_engine(engine)

    added, records = _run(
        get_archetype("chariot")._behavior_probes(state, findings, report, set())
    )

    assert added == 1
    assert len(records) == 1
    assert findings[-1]["category"] == "Comportamento / Reflexão não codificada"
    assert findings[-1]["id"].startswith("F-")


def test_chariot_does_not_probe_on_quick_depths():
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    stub = _stub_client({REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")})
    state = GraphState(target={"name": TARGET}, depth="quick")
    state.set_probe_engine(ProbeEngine(client=stub, respect_robots=False))

    added, records = _run(
        get_archetype("chariot")._behavior_probes(state, findings, report, set())
    )

    assert added == 0
    assert records == []
    assert stub.calls == []


def test_chariot_degrades_when_probe_engine_fails(monkeypatch):
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    state = GraphState(target={"name": TARGET}, depth="deep")

    class Boom:
        async def run(self, **kwargs):
            raise RuntimeError("boom")

    state.set_probe_engine(Boom())
    added, records = _run(
        get_archetype("chariot")._behavior_probes(state, findings, report, set())
    )

    assert added == 0
    assert records == []
    assert len(findings) == len(_reflect_findings(live_body="")[1])


def _multi_session_error_report(*sessions: str) -> tuple[ScanReport, list[dict]]:
    body = "<html><body>Fatal error: undefined variable foo</body></html>"
    report = ScanReport(
        target=TARGET,
        pages=[
            TargetPage(
                url=ERROR_URL,
                status_code=200,
                headers={},
                body=body,
                session=session,
            )
            for session in sessions
        ],
    )
    return report, derive_findings_from_scan(report)


def test_derive_merges_sessions_for_repeated_verbose_url():
    report, findings = _multi_session_error_report("admin", "operator")
    verbose = [f for f in findings if "erro verboso" in f["title"].lower()]
    assert len(verbose) == 1
    assert sorted(verbose[0]["sessions"]) == ["admin", "operator"]
    assert verbose[0]["session"] == "admin"


def test_verbose_leads_probed_with_each_session_client():
    report, findings = _multi_session_error_report("admin", "operator")
    admin = _stub_client({ERROR_URL: _page(ERROR_URL, report.pages[0].body)})
    operator = _stub_client({ERROR_URL: _page(ERROR_URL, report.pages[0].body)})
    default = _stub_client({ERROR_URL: _page(ERROR_URL, report.pages[0].body)})
    engine = ProbeEngine(client=default, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            session_clients={"admin": admin, "operator": operator},
        )
    )

    assert sorted(r["session"] for r in records) == ["admin", "operator"]
    assert admin.calls == [ERROR_URL]
    assert operator.calls == [ERROR_URL]
    assert default.calls == []
    assert behavior[0]["status"] == "candidate"
    assert behavior[0]["extras"]["sessions"] == ["admin", "operator"]


def test_session_without_client_falls_back_to_default():
    report, findings = _multi_session_error_report("user")
    default = _stub_client({ERROR_URL: _page(ERROR_URL, report.pages[0].body)})
    engine = ProbeEngine(client=default, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            session_clients={},
        )
    )

    assert records[0]["session"] == "user"
    assert default.calls == [ERROR_URL]
    assert behavior[0]["extras"]["sessions"] == ["user"]


def test_chariot_forwards_session_clients_to_probe_engine():
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    client = _stub_client(
        {REFLECT_URL: _page(REFLECT_URL, "<html><body>echo: hello</body></html>")}
    )
    captured: dict = {}

    class Engine:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return [], []

    class ScanService:
        def session_clients(self):
            return {"user": client}

    state = GraphState(target={"name": TARGET}, depth="deep")
    state.set_probe_engine(Engine())
    state.set_scan_service(ScanService())

    added, records = _run(
        get_archetype("chariot")._behavior_probes(state, findings, report, set())
    )

    assert added == 0
    assert records == []
    assert captured.get("session_clients") == {"user": client}
    assert client.calls == []


INJECT_URL = "http://example.com/search.php"

UPLOAD_URL = "http://example.com/upload.php"


def _reflection_finding() -> dict:
    return {
        "category": "Aplicação / reflexão observada",
        "extras": {
            "reflections": [
                {"probe_url": f"{INJECT_URL}?q=hello", "param": "q", "value": "hello"}
            ]
        },
    }


def _input_routes_finding(*routes: dict) -> dict:
    return {
        "category": "Aplicação / vetores de entrada",
        "extras": {"routes": list(routes)},
    }


def _injection_probe(replay_body: str, status_code: int = 200) -> str:
    return f"{INJECT_URL}?q=hello"


def test_injection_replay_positive_when_reflected_again():
    report = ScanReport(
        target=TARGET,
        pages=[_page(_injection_probe("hello"), "<html><body>search for hello</body></html>")],
    )
    findings = [
        _reflection_finding(),
        _input_routes_finding(
            {"url": INJECT_URL, "method": "GET", "action": "search.php", "fields": ["q"]}
        ),
    ]
    stub = _stub_client(
        {
            _injection_probe("hello"): _page(
                _injection_probe("hello"), "<html><body>search for hello</body></html>"
            )
        }
    )
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["injection_p1"],
        )
    )

    assert len(behavior) == 1
    assert behavior[0]["category"] == "Comportamento / Injeção suspeita (replay controlado)"
    assert behavior[0]["severity"] == "medium"
    assert records[0]["rule_id"] == "injection_p1"
    assert records[0]["positive"] is True


def test_injection_replay_positive_via_error_status():
    report = ScanReport(
        target=TARGET,
        pages=[_page(_injection_probe("hello"), "<html><body>application error</body></html>")],
    )
    report.pages[0].status_code = 500
    findings = [
        _reflection_finding(),
        _input_routes_finding(
            {
                "url": INJECT_URL,
                "method": "GET",
                "action": "search.php",
                "fields": ["q"],
            }
        ),
    ]

    class _ErrStub:
        user_agent = "ArgusTest"
        calls: list[str] = []

        async def get_page(self, url: str):
            self.calls.append(url)
            return TargetPage(
                url=url,
                status_code=500,
                headers={},
                body="<html><body>application error</body></html>",
            )

        async def fetch_no_rate_limit(self, url: str):
            return TargetPage(
                url=url,
                status_code=200,
                headers={"content-type": "text/plain"},
                body="User-agent: *\nAllow: /",
            )

    engine = ProbeEngine(client=_ErrStub(), respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["injection_p1"],
        )
    )

    assert len(behavior) == 1
    assert records[0]["positive"] is True
    assert records[0]["detail"].startswith("sinal reproduzido")


def test_injection_replay_fp_when_generic_404():
    report = ScanReport(
        target=TARGET,
        pages=[_page(_injection_probe("hello"), "<html><body>404 not found</body></html>")],
    )
    findings = [
        _reflection_finding(),
        _input_routes_finding(
            {
                "url": INJECT_URL,
                "method": "GET",
                "action": "search.php",
                "fields": ["q"],
            }
        ),
    ]
    stub = _stub_client(
        {
            _injection_probe("hello"): _page(
                _injection_probe("hello"), "<html><body>404 not found</body></html>"
            )
        }
    )
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["injection_p1"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False
    assert records[0]["fp_matched"] is True


def test_upload_positive_when_file_input_has_no_accept():
    report = ScanReport(target=TARGET, pages=[_page(UPLOAD_URL, "<html></html>")])
    findings = [
        _input_routes_finding(
            {"url": UPLOAD_URL, "method": "POST", "action": "upload.php", "fields": ["file"]}
        )
    ]
    body = '<form method="POST" action="/upload.php"><input type="file" name="file"></form>'
    stub = _stub_client({UPLOAD_URL: _page(UPLOAD_URL, body)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["upload_p1"],
        )
    )

    assert len(behavior) == 1
    assert behavior[0]["category"] == "Comportamento / Upload sem allowlist de tipo"
    assert records[0]["rule_id"] == "upload_p1"
    assert records[0]["positive"] is True


def test_upload_negative_when_file_input_has_accept():
    report = ScanReport(target=TARGET, pages=[_page(UPLOAD_URL, "<html></html>")])
    findings = [
        _input_routes_finding(
            {"url": UPLOAD_URL, "method": "POST", "action": "upload.php", "fields": ["file"]}
        )
    ]
    body = (
        '<form method="POST" action="/upload.php">'
        '<input type="file" name="file" accept="image/png">'
        "</form>"
    )
    stub = _stub_client({UPLOAD_URL: _page(UPLOAD_URL, body)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["upload_p1"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False


def test_p1_only_runs_with_allowlist():
    report = ScanReport(
        target=TARGET,
        pages=[_page(_injection_probe("hello"), "<html><body>search for hello</body></html>")],
    )
    findings = [
        _reflection_finding(),
        _input_routes_finding(
            {
                "url": INJECT_URL,
                "method": "GET",
                "action": "search.php",
                "fields": ["q"],
            }
        ),
    ]
    stub = _stub_client(
        {
            _injection_probe("hello"): _page(
                _injection_probe("hello"), "<html><body>search for hello</body></html>"
            )
        }
    )
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    # Default seguro: P0 apenas — injeção (P1) fica de fora mesmo com lead ativo.
    assert behavior
    assert all(r["rule_id"] != "injection_p1" for r in records)
    assert all(r["priority"] == "P0" for r in records)


def test_resolve_classes_p1_default_includes_p0_and_p1():
    engine = ProbeEngine(respect_robots=False, default_classes="p1")
    resolved = engine.resolve_classes(None)
    assert {"injection_p1", "upload_p1"} <= set(resolved)
    assert {"reflection_p0", "verbose_error_p0"} <= set(resolved)


ACCOUNT_URL = "http://example.com/account.php"
REDIRECT_URL = "http://example.com/redirect.php"
EXTERNAL_FINAL = "http://evil.test/landed"


def _csrf_finding() -> dict:
    return _input_routes_finding(
        {"url": ACCOUNT_URL, "method": "POST", "action": "account.php", "fields": ["email"]}
    )


def _redirect_routes_finding(*routes: dict) -> dict:
    return {
        "category": "Aplicação / superfície de rotas",
        "extras": {"routes": list(routes)},
    }


def test_csrf_positive_when_post_form_lacks_token():
    report = ScanReport(target=TARGET, pages=[_page(ACCOUNT_URL, "<html></html>")])
    findings = [_csrf_finding()]
    body = (
        '<form method="POST" action="/account.php">'
        '<input type="text" name="email">'
        "</form>"
    )
    stub = _stub_client({ACCOUNT_URL: _page(ACCOUNT_URL, body)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["csrf_p2"],
        )
    )

    assert len(behavior) == 1
    assert behavior[0]["category"] == "Comportamento / POST sem token de estado (CSRF)"
    assert behavior[0]["severity"] == "medium"
    assert records[0]["rule_id"] == "csrf_p2"
    assert records[0]["positive"] is True


def test_csrf_negative_when_token_present():
    report = ScanReport(target=TARGET, pages=[_page(ACCOUNT_URL, "<html></html>")])
    findings = [_csrf_finding()]
    body = (
        '<form method="POST" action="/account.php">'
        '<input type="text" name="email">'
        '<input type="hidden" name="csrf_token" value="tok123">'
        "</form>"
    )
    stub = _stub_client({ACCOUNT_URL: _page(ACCOUNT_URL, body)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["csrf_p2"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False


def test_csrf_fp_when_generic_404():
    report = ScanReport(target=TARGET, pages=[_page(ACCOUNT_URL, "<html></html>")])
    findings = [_csrf_finding()]
    stub = _stub_client(
        {ACCOUNT_URL: _page(ACCOUNT_URL, "<html><body>404 not found</body></html>")}
    )
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["csrf_p2"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False
    assert records[0]["fp_matched"] is True


def test_redirect_positive_when_route_reaches_external_host():
    report = ScanReport(target=TARGET, pages=[_page(REDIRECT_URL, "<html></html>")])
    findings = [
        _redirect_routes_finding(
            {
                "url": EXTERNAL_FINAL,
                "static": False,
                "requested_url": f"{REDIRECT_URL}?next={EXTERNAL_FINAL}",
            }
        )
    ]
    stub = _stub_client(
        {
            f"{REDIRECT_URL}?next={EXTERNAL_FINAL}": TargetPage(
                url=EXTERNAL_FINAL,
                status_code=200,
                headers={},
                body="<html>landed</html>",
            )
        }
    )
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["redirect_p2"],
        )
    )

    assert len(behavior) == 1
    assert behavior[0]["category"] == "Comportamento / Redirecionamento para host externo"
    assert records[0]["rule_id"] == "redirect_p2"
    assert records[0]["positive"] is True


def test_redirect_negative_when_route_stays_on_target():
    report = ScanReport(target=TARGET, pages=[_page(REDIRECT_URL, "<html></html>")])
    findings = [
        _redirect_routes_finding(
            {"url": REDIRECT_URL, "static": False, "requested_url": REDIRECT_URL}
        )
    ]
    stub = _stub_client({REDIRECT_URL: _page(REDIRECT_URL, "<html>home</html>")})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["redirect_p2"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False


def test_redirect_lead_ignores_static_routes():
    report = ScanReport(target=TARGET, pages=[_page(REDIRECT_URL, "<html></html>")])
    findings = [
        {
            "category": "Aplicação / superfície de rotas",
            "extras": {
                "static_routes": [
                    {"url": REDIRECT_URL, "static": True, "requested_url": REDIRECT_URL}
                ]
            },
        }
    ]
    stub = _stub_client({REDIRECT_URL: _page(REDIRECT_URL, "<html>home</html>")})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["redirect_p2"],
        )
    )

    assert behavior == []
    assert records == []
    assert stub.calls == []


def test_route_map_preserves_requested_url():
    page = TargetPage(
        url=EXTERNAL_FINAL,
        status_code=200,
        headers={},
        body="<html><head><title>landed</title></head></html>",
        requested_url=f"{REDIRECT_URL}?next={EXTERNAL_FINAL}",
    )
    report = ScanReport(target=TARGET, pages=[page])
    findings = derive_findings_from_scan(report)

    route_map = next(
        f for f in findings if f["category"] == "Aplicação / superfície de rotas"
    )
    route = route_map["extras"]["routes"][0]
    assert route["url"] == EXTERNAL_FINAL
    assert route["requested_url"] == f"{REDIRECT_URL}?next={EXTERNAL_FINAL}"


def test_p2_only_runs_with_allowlist():
    report = ScanReport(target=TARGET, pages=[_page(ACCOUNT_URL, "<html></html>")])
    findings = [_csrf_finding()]
    body = (
        '<form method="POST" action="/account.php">'
        '<input type="text" name="email">'
        "</form>"
    )
    stub = _stub_client({ACCOUNT_URL: _page(ACCOUNT_URL, body)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    # Default seguro: P0 apenas — CSRF (P2) fica de fora mesmo com lead ativo.
    assert behavior == []
    assert all(r["rule_id"] != "csrf_p2" for r in records)


def test_resolve_classes_p2_default_includes_everything():
    engine = ProbeEngine(respect_robots=False, default_classes="p2")
    resolved = engine.resolve_classes(None)
    assert {"csrf_p2", "redirect_p2"} <= set(resolved)
    assert {"injection_p1", "upload_p1"} <= set(resolved)
    assert {"reflection_p0", "verbose_error_p0"} <= set(resolved)


LOGIN_URL = "http://example.com/login.php"

_LOGIN_FORM = (
    '<form method="POST" action="/login.php">'
    '<input type="text" name="user">'
    '<input type="password" name="pass">'
    "</form>"
)


def _authn_finding() -> dict:
    return _input_routes_finding(
        {
            "url": LOGIN_URL,
            "method": "POST",
            "action": "login.php",
            "fields": ["user", "pass"],
        }
    )


def test_authn_positive_when_login_responses_differ():
    report = ScanReport(target=TARGET, pages=[_page(LOGIN_URL, _LOGIN_FORM)])
    findings = [_authn_finding()]

    def post_fn(url: str, data: dict[str, str]) -> TargetPage:
        if data.get("user") == "admin":
            body = "<html><body>Senha incorreta para admin</body></html>"
        else:
            body = "<html><body>Usuário não localizado</body></html>"
        return TargetPage(url=url, status_code=200, headers={}, body=body)

    stub = _stub_client({LOGIN_URL: _page(LOGIN_URL, _LOGIN_FORM)}, post_fn=post_fn)
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["authn_p3"],
        )
    )

    assert len(behavior) == 1
    assert behavior[0]["category"] == "Comportamento / Login com resposta diferencial (enumeração)"
    assert behavior[0]["severity"] == "medium"
    assert records[0]["rule_id"] == "authn_p3"
    assert records[0]["positive"] is True
    assert "divergiu" in records[0]["detail"]
    assert len(stub.post_calls) == 2


def test_authn_negative_when_login_responses_identical():
    report = ScanReport(target=TARGET, pages=[_page(LOGIN_URL, _LOGIN_FORM)])
    findings = [_authn_finding()]

    def post_fn(url: str, data: dict[str, str]) -> TargetPage:
        return TargetPage(
            url=url,
            status_code=200,
            headers={},
            body="<html><body>invalid credentials</body></html>",
        )

    stub = _stub_client({LOGIN_URL: _page(LOGIN_URL, _LOGIN_FORM)}, post_fn=post_fn)
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["authn_p3"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False
    assert "corpo idêntico" in records[0]["detail"]


def test_authn_fp_when_one_response_is_generic_404():
    report = ScanReport(target=TARGET, pages=[_page(LOGIN_URL, _LOGIN_FORM)])
    findings = [_authn_finding()]

    def post_fn(url: str, data: dict[str, str]) -> TargetPage:
        if data.get("user") == "admin":
            return TargetPage(url=url, status_code=404, headers={}, body="404 not found")
        return TargetPage(
            url=url,
            status_code=200,
            headers={},
            body="<html><body>Usuário não localizado</body></html>",
        )

    stub = _stub_client({LOGIN_URL: _page(LOGIN_URL, _LOGIN_FORM)}, post_fn=post_fn)
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["authn_p3"],
        )
    )

    # Respostas divergem, mas o negativo 404 tem precedência (FP).
    assert behavior == []
    assert records[0]["positive"] is False
    assert records[0]["fp_matched"] is True


def test_authn_negative_when_fresh_page_has_no_login_form():
    report = ScanReport(target=TARGET, pages=[_page(LOGIN_URL, _LOGIN_FORM)])
    findings = [_authn_finding()]
    stub = _stub_client({LOGIN_URL: _page(LOGIN_URL, "<html><body>no form</body></html>")})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["authn_p3"],
        )
    )

    assert behavior == []
    assert records[0]["positive"] is False
    assert "sem form de login" in records[0]["detail"]
    assert stub.post_calls == []


def test_authn_skipped_when_login_action_out_of_host():
    report = ScanReport(target=TARGET, pages=[_page(LOGIN_URL, _LOGIN_FORM)])
    findings = [_authn_finding()]
    cross_host = '<form method="POST" action="http://other.test/login.php">' \
        '<input type="text" name="user"><input type="password" name="pass"></form>'
    stub = _stub_client({LOGIN_URL: _page(LOGIN_URL, cross_host)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(
            report=report,
            findings=findings,
            target={"name": TARGET},
            probe_classes=["authn_p3"],
        )
    )

    assert behavior == []
    assert records[0]["skipped"] is True
    assert "fora do host" in records[0]["skip_reason"]
    assert stub.post_calls == []


def test_p3_only_runs_with_allowlist():
    report = ScanReport(target=TARGET, pages=[_page(LOGIN_URL, _LOGIN_FORM)])
    findings = [_authn_finding()]
    stub = _stub_client({LOGIN_URL: _page(LOGIN_URL, _LOGIN_FORM)})
    engine = ProbeEngine(client=stub, respect_robots=False)

    behavior, records = _run(
        engine.run(report=report, findings=findings, target={"name": TARGET})
    )

    # Default seguro: P0 apenas — authn (P3) fica de fora mesmo com lead ativo.
    assert behavior == []
    assert all(r["rule_id"] != "authn_p3" for r in records)


def test_resolve_classes_p3_default_includes_everything():
    engine = ProbeEngine(respect_robots=False, default_classes="p3")
    resolved = engine.resolve_classes(None)
    assert {"authn_p3", "csrf_p2", "redirect_p2"} <= set(resolved)
    assert {"injection_p1", "upload_p1"} <= set(resolved)
    assert {"reflection_p0", "verbose_error_p0"} <= set(resolved)


def _dup_policy(policy_id: str):
    """The reflection policy, reselected so two policies share one endpoint."""
    from app.probing.schemas import ProbePolicy

    return ProbePolicy.model_validate(
        {
            "id": policy_id,
            "version": "1.0.0",
            "name": "dup",
            "priority": "P0",
            "class_label": "Reflexão não codificada",
            "description": "dup",
            "precondition": {"lead": "reflection"},
            "allowed_probe": {"tool": "http_request", "method": "GET"},
            "positive_signal": [{"kind": "reflects_param"}],
            "negative_signal": [],
            "candidate_severity": "low",
            "reporting": {
                "title_template": "{count} reflexão(ões)",
                "remediation": "remediar",
                "references": [],
                "confidence": 0.6,
            },
        }
    )


def _yaml(policy_id: str) -> str:
    return yaml.safe_dump(
        {
            "id": policy_id,
            "version": "1.0.0",
            "name": policy_id,
            "priority": "P0",
            "class_label": "Classe",
            "description": "desc",
            "precondition": {"lead": "reflection"},
            "allowed_probe": {"tool": "http_request", "method": "GET"},
            "positive_signal": [{"kind": "reflects_param"}],
            "negative_signal": [],
            "candidate_severity": "low",
            "requires_hitl": True,
            "default_enabled": True,
            "reporting": {
                "title_template": "{count} lead(s)",
                "remediation": "remediar",
                "references": [],
                "confidence": 0.6,
            },
        }
    )