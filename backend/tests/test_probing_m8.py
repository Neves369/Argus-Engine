from __future__ import annotations

import asyncio

from app.probing.engine import ProbeEngine
from app.probing.schemas import SignalRule
from app.scanning.client import ScanError
from app.scanning.service import ScanReport
from app.scanning.spec import TargetPage

TARGET = "example.com"
BASE = "http://example.com/"
ROOT = BASE
USERS_API = BASE + "api/users"
HEALTH_API = BASE + "api/health"


def _run(coro):
    return asyncio.run(coro)


def _page(url: str, body: str, status_code: int = 200) -> TargetPage:
    return TargetPage(url=url, status_code=status_code, headers={}, body=body)


def _stub_client(pages: dict[str, TargetPage]) -> object:
    class _StubClient:
        user_agent = "ArgusTest"

        def __init__(self) -> None:
            self.pages = pages
            self.calls: list[str] = []

        async def get_page(self, url: str):
            self.calls.append(url)
            page = self.pages.get(url)
            if page is None:
                raise ScanError(f"no stub for {url}")
            return page

    return _StubClient()


def _endpoint(
    url: str,
    *,
    path: str | None = None,
    params: list[str] | None = None,
    session: str = "anon",
) -> dict:
    return {
        "method": "GET",
        "path": path or url.rsplit("/", 1)[-1],
        "params": params or [],
        "session": session,
        "url": url,
    }


def _api_report(*endpoints: dict) -> ScanReport:
    return ScanReport(
        target=TARGET,
        pages=[_page(ROOT, "<html><body>root</body></html>")],
        api_endpoints=list(endpoints),
    )


def _run_engine(
    report: ScanReport,
    client: object,
    classes: list[str],
    *,
    session_clients=None,
    max_probes: int = 10,
) -> tuple[list[dict], list[dict]]:
    engine = ProbeEngine(
        client=client,
        respect_robots=False,
        max_probes=max_probes,
        session_clients=session_clients,
    )
    return _run(
        engine.run(
            report=report,
            findings=[],
            target={"name": TARGET},
            probe_classes=classes,
            session_clients=session_clients,
        )
    )


def test_schema_accepts_api_lead_and_json_signals():
    rule = SignalRule(kind="json_contains", value="traceback")
    assert rule.kind == "json_contains"
    assert SignalRule(kind="json_has_array").value is None
    assert SignalRule(kind="json_response").kind == "json_response"


def test_api_json_error_positive_on_5xx_json():
    body = '{"error": "Internal Server Error", "detail": "traceback: div by zero"}'
    report = _api_report(_endpoint(USERS_API))
    stub = _stub_client({USERS_API: _page(USERS_API, body, status_code=500)})

    behavior, records = _run_engine(report, stub, ["api_json_error_p0"])

    assert len(behavior) == 1
    finding = behavior[0]
    assert finding["category"] == "Comportamento / Erro verboso em resposta JSON"
    assert finding["status"] == "candidate"
    assert finding["extras"]["rule_ids"] == ["api_json_error_p0"]
    assert records[0]["positive"] is True
    assert records[0]["status_code"] == 500
    assert records[0]["session"] == "anon"


def test_api_json_error_positive_on_markers_without_5xx():
    body = '{"ok": false, "message": "Exception: null pointer"}'
    report = _api_report(_endpoint(HEALTH_API))
    stub = _stub_client({HEALTH_API: _page(HEALTH_API, body)})

    behavior, records = _run_engine(report, stub, ["api_json_error_p0"])

    assert len(behavior) == 1
    assert records[0]["positive"] is True


def test_api_json_error_negative_on_not_found():
    report = _api_report(_endpoint(USERS_API))
    stub = _stub_client({USERS_API: _page(USERS_API, "<h1>not found</h1>", status_code=404)})

    behavior, records = _run_engine(report, stub, ["api_json_error_p0"])

    assert behavior == []
    assert records[0]["positive"] is False
    assert records[0]["fp_matched"] is True


def test_api_json_error_ignores_plain_object_without_markers():
    report = _api_report(_endpoint(HEALTH_API))
    stub = _stub_client({HEALTH_API: _page(HEALTH_API, '{"status": "ok"}')})

    behavior, records = _run_engine(report, stub, ["api_json_error_p0"])

    assert behavior == []
    assert records[0]["positive"] is False


def test_api_bulk_positive_on_json_array():
    body = '{"data": [{"id": 1}, {"id": 2}]}'
    report = _api_report(_endpoint(USERS_API, params=["limit", "page"]))
    stub = _stub_client({USERS_API: _page(USERS_API, body)})

    behavior, records = _run_engine(report, stub, ["api_bulk_p1"])

    assert len(behavior) == 1
    assert (
        behavior[0]["category"]
        == "Comportamento / Retorno abrangente em API (coleção sem filtro)"
    )
    assert records[0]["positive"] is True


def test_api_bulk_not_positive_on_plain_object():
    report = _api_report(_endpoint(USERS_API))
    stub = _stub_client({USERS_API: _page(USERS_API, '{"id": 1, "name": "alice"}')})

    behavior, records = _run_engine(report, stub, ["api_bulk_p1"])

    assert behavior == []
    assert records[0]["positive"] is False


def test_api_bulk_not_positive_on_non_json():
    report = _api_report(_endpoint(USERS_API))
    stub = _stub_client({USERS_API: _page(USERS_API, "<html>login page</html>")})

    behavior, records = _run_engine(report, stub, ["api_bulk_p1"])

    assert behavior == []
    assert records[0]["positive"] is False


def test_api_bulk_negative_when_endpoint_requires_auth():
    report = _api_report(_endpoint(USERS_API))
    stub = _stub_client({USERS_API: _page(USERS_API, '{"error": "unauthorized"}', status_code=403)})

    behavior, records = _run_engine(report, stub, ["api_bulk_p1"])

    assert behavior == []
    assert records[0]["fp_matched"] is True
    assert records[0]["positive"] is False


def test_api_leads_send_bare_url_without_invented_values():
    report = _api_report(_endpoint(USERS_API, params=["limit", "page", "q"]))
    stub = _stub_client({USERS_API: _page(USERS_API, '{"data": []}')})

    _behavior, records = _run_engine(report, stub, ["api_bulk_p1"])

    assert stub.calls == [USERS_API]
    assert "?" not in records[0]["url"]


def test_api_probes_use_session_client_per_role():
    admin_body = '{"data": [{"id": 9}]}'
    default_stub = _stub_client(
        {USERS_API: _page(USERS_API, '{"error": "unauthorized"}', status_code=403)}
    )
    admin_stub = _stub_client({USERS_API: _page(USERS_API, admin_body)})
    report = _api_report(_endpoint(USERS_API, session="admin"))

    behavior, records = _run_engine(
        report,
        default_stub,
        ["api_bulk_p1"],
        session_clients={"admin": admin_stub},
    )

    assert len(behavior) == 1
    assert records[0]["session"] == "admin"
    assert records[0]["positive"] is True
    assert admin_stub.calls == [USERS_API]
    assert default_stub.calls == []


def test_api_probes_respect_robots_disallow():
    report = _api_report(_endpoint(USERS_API))
    stub = _stub_client({USERS_API: _page(USERS_API, '{"data": []}')})
    engine = ProbeEngine(client=stub, respect_robots=True, max_probes=10)

    async def _run_with_robots():
        engine._robots_cache["example.com"] = _AllowNone()
        return await engine.run(
            report=report,
            findings=[],
            target={"name": TARGET},
            probe_classes=["api_bulk_p1"],
        )

    behavior, records = _run(_run_with_robots())

    assert behavior == []
    assert records[0]["skipped"] is True
    assert records[0]["skip_reason"] == "robots disallow"
    assert stub.calls == []


class _AllowNone:
    def is_allowed(self, path: str) -> bool:  # noqa: ARG002
        return False


def test_api_json_error_in_default_p0_allowlist_but_bulk_not():
    engine = ProbeEngine(respect_robots=False)
    resolved = engine.resolve_classes(None)
    assert "api_json_error_p0" in resolved
    assert "api_bulk_p1" not in resolved