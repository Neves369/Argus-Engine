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
) -> object:
    class _StubClient:
        user_agent = "ArgusTest"

        def __init__(self) -> None:
            self.pages = pages
            self.robots_body = robots_body or "User-agent: *\nAllow: /"
            self.calls: list[str] = []

        async def get_page(self, url: str):
            self.calls.append(url)
            page = self.pages.get(url)
            if page is None:
                raise ScanError(f"no stub for {url}")
            return page

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


def test_catalog_loads_the_p0_policies():
    catalog = load_catalog()
    assert sorted(catalog) == ["reflection_p0", "verbose_error_p0"]
    assert all(p.priority == "P0" for p in catalog.values())
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
    state = GraphState(target={"name": TARGET})
    state.set_probe_engine(engine)

    added, records = _run(
        get_archetype("chariot")._behavior_probes(state, findings, report, set())
    )

    assert added == 1
    assert len(records) == 1
    assert findings[-1]["category"] == "Comportamento / Reflexão não codificada"
    assert findings[-1]["id"].startswith("F-")


def test_chariot_degrades_when_probe_engine_fails(monkeypatch):
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    report, findings = _reflect_findings(live_body="<html><body>echo: hello</body></html>")
    state = GraphState(target={"name": TARGET})

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