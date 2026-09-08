from __future__ import annotations

import asyncio

from app.agents import get_archetype
from app.orchestration.state import GraphState
from app.scanning.client import ScanError
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage
from app.scanning.verify import VerificationService
from app.tools.executor import ToolExecutionError
from app.tools.spec import ToolKind, ToolSpec

_MISSING_FINDING = {
    "title": "Headers de segurança ausentes na resposta",
    "probe_url": "http://example.com/",
    "affected": "example.com",
}


def _run(coro):
    return asyncio.run(coro)


def _stub_client(pages: dict[str, TargetPage], robots_body: str | None = None):
    class _StubClient:
        user_agent = "ArgusTest"

        def __init__(self) -> None:
            self.pages = pages
            self.robots_body = robots_body or "User-agent: *\nAllow: /"
            self.calls: list[str] = []
            self.probes: list[str] = []

        async def get_page(self, url: str):
            self.calls.append(url)
            self.probes.append(url)
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


def _no_security_headers(*, url: str = "http://example.com/") -> TargetPage:
    return TargetPage(
        url=url,
        status_code=200,
        headers={"content-type": "text/html"},
        body="<html><body>ok</body></html>",
    )


def _patched_page(*, url: str = "http://example.com/") -> TargetPage:
    return TargetPage(
        url=url,
        status_code=200,
        headers={
            "content-type": "text/html",
            "content-security-policy": "default-src 'none'",
            "strict-transport-security": "max-age=31536000",
            "x-frame-options": "DENY",
            "x-content-type-options": "nosniff",
            "referrer-policy": "no-referrer",
            "permissions-policy": "camera=()",
        },
        body="<html><body>ok</body></html>",
    )


# ---------------------------------------------------------------------------
# VerificationService — sondas ao vivo (confirmar / refutar / pular / teto)
# ---------------------------------------------------------------------------


def test_verifier_confirms_candidate_from_fresh_probe():
    client = _stub_client({"http://example.com/": _no_security_headers()})
    service = VerificationService(client=client, respect_robots=False)
    report = ScanReport(target="example.com", pages=[_no_security_headers()])

    outcomes = _run(
        service.verify(
            report=report,
            findings=[dict(_MISSING_FINDING)],
            target={"name": "example.com"},
        )
    )

    assert outcomes == [outcomes[0]]
    out = outcomes[0]
    assert out is not None
    assert out["confirmed"] is True
    assert out["probe"]["skipped"] is False
    assert out["probe"]["status_code"] == 200
    assert out["probe"]["url"] == "http://example.com/"


def test_verifier_refutes_when_fresh_response_is_patched():
    client = _stub_client({"http://example.com/": _patched_page()})
    service = VerificationService(client=client, respect_robots=False)
    report = ScanReport(target="example.com", pages=[_no_security_headers()])

    out = _run(
        service.verify(
            report=report,
            findings=[dict(_MISSING_FINDING)],
            target={"name": "example.com"},
        )
    )[0]

    assert out is not None
    assert out["confirmed"] is False
    assert out["probe"]["skipped"] is False


def test_verifier_skips_probe_disallowed_by_robots():
    client = _stub_client({}, robots_body="User-agent: *\nDisallow: /")
    service = VerificationService(client=client, respect_robots=True)
    report = ScanReport(target="example.com", pages=[_no_security_headers()])

    out = _run(
        service.verify(
            report=report,
            findings=[dict(_MISSING_FINDING)],
            target={"name": "example.com"},
        )
    )[0]

    assert out is not None
    assert out["confirmed"] is False
    assert out["probe"]["skipped"] is True
    assert out["probe"]["skip_reason"] == "robots disallow"
    assert client.probes == [], "probe não pode ser enviado"


def test_verifier_honors_max_probes_cap():
    client = _stub_client({"http://example.com/": _no_security_headers()})
    service = VerificationService(client=client, respect_robots=False, max_probes=1)
    report = ScanReport(target="example.com")
    findings = [
        dict(_MISSING_FINDING),
        {**_MISSING_FINDING, "probe_url": "http://other.example.com/"},
    ]

    outcomes = _run(
        service.verify(report=report, findings=findings, target={"name": "example.com"})
    )

    assert outcomes[0] is not None
    assert outcomes[1] is None
    assert len(client.calls) == 1


def test_verifier_disabled_or_out_of_scope_returns_none():
    service = VerificationService(client=_stub_client({}), enabled=False)
    report = ScanReport(target="example.com")
    assert _run(service.verify(report=report, findings=[dict(_MISSING_FINDING)])) == [None]

    client = _stub_client({})
    service = VerificationService(client=client, respect_robots=False)
    assert _run(
        service.verify(
            report=report,
            findings=[dict(_MISSING_FINDING)],
            target={"name": "evil.org"},
        )
    ) == [None]
    assert client.calls == []


def test_verifier_falls_back_to_http_when_https_unreachable():
    client = _stub_client({"http://example.com/": _no_security_headers()})
    service = VerificationService(client=client, respect_robots=False)
    report = ScanReport(target="example.com")
    finding = dict(_MISSING_FINDING)
    finding["probe_url"] = "https://example.com/"

    out = _run(service.verify(report=report, findings=[finding], target={"name": "example.com"}))[0]

    assert out is not None
    assert out["probe"]["url"] == "http://example.com/"
    assert out["confirmed"] is True


def test_finding_without_probeable_url_is_left_unverified():
    client = _stub_client({})
    service = VerificationService(client=client, respect_robots=False)
    report = ScanReport(target="example.com")

    outcomes = _run(
        service.verify(
            report=report,
            findings=[{"title": "lead sem url", "affected": ""}],
            target={"name": "example.com"},
        )
    )

    assert outcomes == [None]
    assert client.calls == []


# ---------------------------------------------------------------------------
# Chariot — camada de execução real (probes + tools do operador)
# ---------------------------------------------------------------------------


class _FakeScanService:
    def __init__(self, report: ScanReport) -> None:
        self._report = report

    async def scan(self, target: dict) -> ScanReport:
        return self._report


class _FakeVerifier:
    def __init__(self, outcomes: list[dict | None], error: Exception | None = None) -> None:
        self._outcomes = outcomes
        self._error = error

    async def verify(self, *, report, findings, target=None):
        if self._error is not None:
            raise self._error
        return self._outcomes


class _FakeRegistry:
    def __init__(self, specs: list[ToolSpec]) -> None:
        self._specs = specs

    def specs(self) -> list[ToolSpec]:
        return self._specs


class _FakeExecutor:
    def __init__(self, specs: list[ToolSpec], error: Exception | None = None) -> None:
        self.registry = _FakeRegistry(specs)
        self.invoked: list[str] = []
        self._error = error

    async def execute(self, name: str, params: dict | None = None, *, devil_mode: bool = False):
        self.invoked.append(name)
        if self._error is not None:
            raise self._error
        return {"tool": name, "status_code": 200, "body": "ok"}


def _chariot_state(report: ScanReport | None) -> GraphState:
    state = GraphState(
        target={"name": "example.com", "url": "http://example.com/"},
        composition=["chariot"],
    )
    if report is not None:
        state.set_scan_service(_FakeScanService(report))
    return state


def _probe_outcome() -> dict:
    return {
        "confirmed": True,
        "probe": {
            "url": "http://example.com/",
            "status_code": 200,
            "final_url": "http://example.com/",
            "headers": {},
            "observed_at": "2026-01-01T00:00:00+00:00",
            "skipped": False,
            "skip_reason": None,
        },
    }


def test_chariot_live_mode_probes_and_runs_non_destructive_tools():
    chariot = get_archetype("chariot")
    state = _chariot_state(ScanReport(target="example.com", pages=[_no_security_headers()]))
    state.set_verification_service(_FakeVerifier([_probe_outcome()]))
    executor = _FakeExecutor(
        [
            ToolSpec(name="page-check", kind=ToolKind.HTTP, destructive=False),
            ToolSpec(name="nmap", kind=ToolKind.CLI, command="nmap", destructive=True),
        ]
    )
    state.set_tool_executor(executor)

    update = _run(chariot.run(state))

    entry = update["history"][-1]
    assert entry["agent"] == "chariot"
    assert entry["action"] == "safety"
    assert entry["mode"] == "live"
    assert entry["verified"] == 1
    assert entry["refuted"] == 0
    assert entry["tools_tried"] == 1
    assert len(entry["tool_runs"]) == 1
    assert entry["tool_runs"][0]["tool"] == "page-check"
    assert entry["tool_runs"][0]["outcome"] == "ok"
    assert executor.invoked == ["page-check"], "tool destrutiva nunca roda em modo normal"
    scan_findings = [f for f in update["findings"] if "probe_url" in f]
    assert scan_findings and scan_findings[0]["verification"]["confirmed"] is True


def test_chariot_live_mode_counts_refuted_probes():
    chariot = get_archetype("chariot")
    state = _chariot_state(ScanReport(target="example.com", pages=[_no_security_headers()]))
    refuted = _probe_outcome()
    refuted["confirmed"] = False
    state.set_verification_service(_FakeVerifier([refuted]))

    update = _run(chariot.run(state))

    entry = update["history"][-1]
    assert entry["mode"] == "live"
    assert entry["verified"] == 0
    assert entry["refuted"] == 1


def test_chariot_without_services_runs_simulate():
    chariot = get_archetype("chariot")
    state = _chariot_state(report=None)

    update = _run(chariot.run(state))

    entry = update["history"][-1]
    assert entry["action"] == "safety"
    assert entry["mode"] == "simulate"
    assert entry.get("verified") is None
    assert entry.get("refuted") is None
    assert entry.get("tools_tried") is None
    assert "tool_runs" not in entry


def test_chariot_degrades_when_tool_fails():
    chariot = get_archetype("chariot")
    state = _chariot_state(ScanReport(target="example.com", pages=[_no_security_headers()]))
    state.set_verification_service(_FakeVerifier([_probe_outcome()]))
    state.set_tool_executor(
        _FakeExecutor(
            [ToolSpec(name="broken", kind=ToolKind.CLI, command="true")],
            error=ToolExecutionError("tool exploded"),
        )
    )

    update = _run(chariot.run(state))

    entry = update["history"][-1]
    assert entry["mode"] == "live"
    assert entry["tools_tried"] == 1
    assert entry["verified"] == 1, "ferramenta falhou mas a verificação ao vivo continua valendo"
    assert entry["tool_runs"][0]["outcome"] == "failed"
    assert "tool exploded" in entry["tool_runs"][0]["detail"]["note"]


def test_chariot_degrades_when_verifier_errors():
    chariot = get_archetype("chariot")
    state = _chariot_state(ScanReport(target="example.com", pages=[_no_security_headers()]))
    state.set_verification_service(_FakeVerifier([], error=RuntimeError("probe boom")))

    update = _run(chariot.run(state))

    entry = update["history"][-1]
    assert entry["action"] == "safety"
    assert entry["findings"] >= 1
    assert not any("verification" in f for f in update["findings"])