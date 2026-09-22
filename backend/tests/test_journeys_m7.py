from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.core.security import (
    activate_kill_switch,
    deactivate_kill_switch,
    is_kill_switch_active,
)
from app.journeys.catalog import (
    default_journey_ids,
    journey_digest,
    journey_manifest,
    load_catalog,
)
from app.journeys.engine import JourneyEngine
from app.journeys.schemas import (
    Journey,
    JourneyExpect,
    JourneyReporting,
    JourneyStep,
)
from app.scanning.client import ScanError
from app.scanning.spec import TargetPage

TARGET = "example.com"
BASE = "https://example.com/"


def _run(coro):
    return asyncio.run(coro)


def _page(url: str, body: str = "", status_code: int = 200) -> TargetPage:
    return TargetPage(url=url, status_code=status_code, headers={}, body=body)


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


def _step(
    name: str,
    path: str,
    *,
    method: str = "GET",
    contains: str | None = None,
    statuses: tuple[int, ...] = (200,),
) -> JourneyStep:
    return JourneyStep(
        name=name,
        method=method,
        path=path,
        expect=JourneyExpect(status_in=list(statuses), contains=contains),
    )


def _journey(
    jid: str = "test_journey",
    steps: list[JourneyStep] | None = None,
    *,
    priority: str = "P0",
    run_anonymous: bool = True,
) -> Journey:
    return Journey(
        id=jid,
        version="1.0.0",
        name=jid,
        priority=priority,
        description="jornada de teste",
        steps=steps or [_step("Passo 1", "/")],
        run_anonymous=run_anonymous,
        default_enabled=True,
        candidate_severity="low",
        requires_hitl=True,
        reporting=JourneyReporting(
            title_template="Jornada {name}: efeito divergiu entre sessões",
            remediation="revise o controle de acesso",
            confidence=0.5,
        ),
    )


def test_journey_catalog_loads_and_allowlist():
    catalog = load_catalog()
    assert sorted(catalog) == ["account_self_p1", "admin_area_p0"]
    assert default_journey_ids("p0") == ["admin_area_p0"]
    assert default_journey_ids("p1") == ["account_self_p1", "admin_area_p0"]
    manifest = journey_manifest()
    assert manifest["journeys"]["admin_area_p0"]["sha256"]
    assert journey_digest(catalog["admin_area_p0"]) != journey_digest(
        catalog["account_self_p1"]
    )


def test_journey_catalog_fails_closed_on_duplicate_id(tmp_path, monkeypatch):
    import app.journeys.catalog as catalog_mod

    (tmp_path / "a.yaml").write_text(
        "id: dup\nversion: '1.0.0'\nname: A\npriority: P0\ndescription: x\n"
        "steps:\n  - name: g\n    path: /\n"
        "reporting:\n  title_template: 'J {name}'\n  remediation: x\n"
    )
    (tmp_path / "b.yaml").write_text(
        "id: dup\nversion: '1.0.0'\nname: B\npriority: P0\ndescription: x\n"
        "steps:\n  - name: g\n    path: /\n"
        "reporting:\n  title_template: 'J {name}'\n  remediation: x\n"
    )
    monkeypatch.setattr(catalog_mod, "JOURNEYS_PATH", tmp_path)
    catalog_mod.load_catalog.cache_clear()
    try:
        with pytest.raises(ValueError, match="Duplicate journey id"):
            catalog_mod.load_catalog()
    finally:
        catalog_mod.load_catalog.cache_clear()


def test_journey_catalog_fails_closed_on_invalid_yaml(tmp_path, monkeypatch):
    import app.journeys.catalog as catalog_mod

    (tmp_path / "bad.yaml").write_text(
        "id: broken\nversion: '1.0.0'\npriority: P0\n"
    )
    monkeypatch.setattr(catalog_mod, "JOURNEYS_PATH", tmp_path)
    catalog_mod.load_catalog.cache_clear()
    try:
        with pytest.raises((ValueError, ValidationError)):
            catalog_mod.load_catalog()
    finally:
        catalog_mod.load_catalog.cache_clear()


def test_journey_divergence_between_roles_creates_finding():
    steps = [
        _step("Abrir painel", "/admin/", contains="painel"),
        _step("Listar recursos", "/admin/resources", contains="tabela"),
    ]
    journey = _journey("admin_area", steps=steps)
    anon = _stub_client(
        {
            "https://example.com/admin/": _page(
                "https://example.com/login", status_code=302
            ),
            "https://example.com/admin/resources": _page(
                "https://example.com/login", status_code=302
            ),
        }
    )
    admin = _stub_client(
        {
            "https://example.com/admin/": _page(
                "https://example.com/admin/", "<h1>painel</h1>"
            ),
            "https://example.com/admin/resources": _page(
                "https://example.com/admin/resources", "<h1>tabela</h1>"
            ),
        }
    )
    operator = _stub_client(
        {
            "https://example.com/admin/": _page(
                "https://example.com/admin/", status_code=404
            ),
            "https://example.com/admin/resources": _page(
                "https://example.com/admin/resources", status_code=403
            ),
        }
    )
    engine = JourneyEngine(catalog={journey.id: journey}, respect_robots=False)

    behavior, records = _run(
        engine.run(
            target={"name": TARGET},
            session_clients={"admin": admin, "operator": operator},
            anon_client=anon,
        )
    )

    assert len(records) == 6
    assert len(behavior) == 1
    finding = behavior[0]
    assert finding["status"] == "candidate"
    assert finding["requires_human_review"] is True
    assert finding["category"] == "Comportamento / Jornada / admin_area"
    assert finding["title"] == "Jornada admin_area: efeito divergiu entre sessões"
    assert finding["extras"]["journey"]["id"] == "admin_area"
    assert finding["extras"]["sessions"] == ["admin", "anon", "operator"]
    steps_out = finding["extras"]["divergent_steps"]
    assert len(steps_out) == 2
    assert steps_out[0]["sessions_cs"] == ["admin"]
    assert steps_out[0]["sessions_failed"] == ["anon", "operator"]
    assert any(r["session"] == "admin" and r["effect_ok"] for r in records)
    assert any(r["session"] == "anon" and not r["effect_ok"] for r in records)


def test_journey_no_divergence_returns_no_finding():
    journey = _journey("public_home", steps=[_step("Home", "/", contains="oi")])
    anon = _stub_client({"https://example.com/": _page("", "<h1>oi</h1>")})
    admin = _stub_client({"https://example.com/": _page("", "<h1>oi</h1>")})
    engine = JourneyEngine(catalog={journey.id: journey}, respect_robots=False)

    behavior, records = _run(
        engine.run(
            target={"name": TARGET},
            session_clients={"admin": admin},
            anon_client=anon,
        )
    )

    assert behavior == []
    assert len(records) == 2
    assert all(r["effect_ok"] for r in records)


def test_journey_post_step_uses_post_page():
    journey = _journey(
        "submit_flow",
        steps=[
            JourneyStep(
                name="Enviar",
                method="POST",
                path="/submit",
                body={"q": "x"},
                expect=JourneyExpect(status_in=[200, 201], contains="ok"),
            )
        ],
        run_anonymous=False,
    )

    def _post(url, data):
        return _page(url, "ok", status_code=201)

    client = _stub_client({}, post_fn=_post)
    engine = JourneyEngine(catalog={journey.id: journey}, respect_robots=False)

    behavior, records = _run(
        engine.run(target={"name": TARGET}, session_clients={"admin": client})
    )

    assert behavior == []
    assert len(records) == 1
    assert records[0]["method"] == "POST"
    assert records[0]["status_code"] == 201
    assert records[0]["effect_ok"] is True
    assert client.post_calls == [("https://example.com/submit", {"q": "x"})]


def test_journey_robots_disallow_skips_steps_auditably():
    journey = _journey(
        "admin_area", steps=[_step("Painel", "/admin/", contains="painel")]
    )
    stub = _stub_client(
        {
            "https://example.com/admin/": _page(
                "https://example.com/admin/", "<h1>painel</h1>"
            )
        },
        robots_body="User-agent: *\nDisallow: /admin/",
    )
    engine = JourneyEngine(
        catalog={journey.id: journey}, respect_robots=True, client=stub
    )

    behavior, records = _run(
        engine.run(target={"name": TARGET}, session_clients={}, anon_client=stub)
    )

    assert behavior == []
    assert len(records) == 1
    assert records[0]["skipped"] is True
    assert records[0]["skip_reason"] == "robots disallow"


def test_journey_out_of_scope_runs_nothing():
    journey = _journey()
    stub = _stub_client({"https://evil.org/": _page("", "oi")})
    engine = JourneyEngine(catalog={journey.id: journey}, respect_robots=False)

    behavior, records = _run(
        engine.run(target={"name": "evil.org"}, session_clients={}, anon_client=stub)
    )

    assert behavior == []
    assert records == []
    assert stub.calls == []


def test_journey_kill_switch_blocks():
    journey = _journey()
    stub = _stub_client({"https://example.com/": _page("", "oi")})
    engine = JourneyEngine(catalog={journey.id: journey}, respect_robots=False)

    activate_kill_switch()
    try:
        behavior, records = _run(
            engine.run(target={"name": TARGET}, session_clients={}, anon_client=stub)
        )
    finally:
        deactivate_kill_switch()

    assert not is_kill_switch_active()
    assert behavior == []
    assert records == []
    assert stub.calls == []


def test_journey_max_steps_cap_is_enforced():
    journey = _journey(
        "cap",
        steps=[
            _step("P1", "/a", contains="a"),
            _step("P2", "/b", contains="b"),
        ],
    )
    anon = _stub_client(
        {
            "https://example.com/a": _page("", "a"),
            "https://example.com/b": _page("", "b"),
        }
    )
    admin = _stub_client(
        {
            "https://example.com/a": _page("", "a"),
            "https://example.com/b": _page("", "b"),
        }
    )
    engine = JourneyEngine(
        catalog={journey.id: journey}, respect_robots=False, max_steps_per_session=2
    )

    behavior, records = _run(
        engine.run(
            target={"name": TARGET},
            session_clients={"admin": admin},
            anon_client=anon,
        )
    )

    capped = [r for r in records if r["skip_reason"] == "max steps cap"]
    assert len(capped) == 2
    assert len([r for r in records if not r.get("skipped")]) == 2


def test_journey_requested_ids_respect_allowlist_for_existing_only():
    p0 = _journey("j_p0", priority="P0")
    p1 = _journey("j_p1", priority="P1")
    engine = JourneyEngine(
        catalog={"j_p0": p0, "j_p1": p1}, respect_robots=False, default_classes="p0"
    )
    assert engine.active_journeys(None) == ["j_p0"]
    assert engine.active_journeys(["j_p1", "nao_existe"]) == ["j_p1"]


def test_chariot_runs_journeys_on_deep_and_forwards_session_clients():
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    captured: dict = {}

    class Engine:
        async def run(self, **kwargs):
            captured.update(kwargs)
            return [], []

    class ScanService:
        def session_clients(self):
            return {"admin": "client-admin"}

    state = GraphState(target={"name": TARGET}, depth="deep")
    state.set_journey_engine(Engine())
    state.set_scan_service(ScanService())

    added, records = _run(
        get_archetype("chariot")._journeys(state, [], set())
    )

    assert added == 0
    assert records == []
    assert captured.get("session_clients") == {"admin": "client-admin"}


def test_chariot_does_not_journey_on_quick_depths():
    from app.agents import get_archetype
    from app.orchestration.state import GraphState

    calls = []

    class Engine:
        async def run(self, **kwargs):
            calls.append(kwargs)
            return [], []

    state = GraphState(target={"name": TARGET}, depth="quick")
    state.set_journey_engine(Engine())

    added, records = _run(
        get_archetype("chariot")._journeys(state, [], set())
    )

    assert added == 0
    assert records == []
    assert calls == []


def test_journey_finding_lands_in_report_comportamento():
    from app.db.models import Finding, Run
    from app.services.export import (
        finding_report,
        finding_section,
        run_report,
        run_report_markdown,
    )

    journey = _journey("admin_area", steps=[_step("Abrir painel", "/admin/")])
    anon = _stub_client(
        {"https://example.com/admin/": _page("https://example.com/login", status_code=302)}
    )
    admin = _stub_client(
        {"https://example.com/admin/": _page("", "painel")}
    )
    engine = JourneyEngine(catalog={journey.id: journey}, respect_robots=False)

    behavior, records = _run(
        engine.run(
            target={"name": TARGET},
            session_clients={"admin": admin},
            anon_client=anon,
        )
    )
    assert len(behavior) == 1

    finding = Finding(
        title=behavior[0]["title"],
        severity=behavior[0]["severity"],
        category=behavior[0]["category"],
        affected="example.com",
        confidence=behavior[0]["confidence"],
        status=behavior[0]["status"],
        requires_human_review=behavior[0]["requires_human_review"],
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
    rendered = finding_report(finding)
    assert "divergent_steps" in rendered["extras"]