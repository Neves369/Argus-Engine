from __future__ import annotations

import asyncio
from unittest import mock

import httpx
import pytest
import respx

from app.core.config import get_settings
from app.core.security import activate_kill_switch, deactivate_kill_switch
from app.scanning.client import ScanHTTPClient
from app.tools import ToolExecutionError, ToolExecutor, ToolRegistry
from app.tools.http_tools import HttpToolHandler
from app.tools.spec import ToolKind, ToolSpec


def _run(coro):
    return asyncio.run(coro)


def _handler(*, client: ScanHTTPClient | None = None) -> HttpToolHandler:
    return HttpToolHandler(
        client=client or ScanHTTPClient(rate_limit=0),
        respect_robots=False,
    )


def _registry(*specs: ToolSpec) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


_LOGIN_HTML = """<html><body><form action="/authenticate" method="post">
<input type="text" name="username"/>
<input type="password" name="password"/>
</form></body></html>"""


# ---------------------------------------------------------------------------
# Manifesto: tools scanner registradas
# ---------------------------------------------------------------------------


def test_scanner_tools_registered_in_manifest():
    registry = ToolRegistry()
    registry.load(get_settings().tools_manifest)
    for name in ("http_request", "session_login", "form_discover", "http_header_probe"):
        spec = registry.get_tool(name)
        assert spec.kind == ToolKind.SCANNER
        assert spec.destructive is False


# ---------------------------------------------------------------------------
# HttpToolHandler — comportamento por handler
# ---------------------------------------------------------------------------


@respx.mock
def test_http_request_returns_status_headers_body():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            headers={"Server": "nginx", "X-Custom": "1"},
            text="<html>hello</html>",
        )
    )
    handler = _handler()

    result = _run(handler.handle("http_request", {"url": "http://example.com/"}))

    assert result["tool"] == "http_request"
    assert result["status_code"] == 200
    assert result["headers"]["server"] == "nginx"
    assert "<html>hello</html>" in result["body"]


@respx.mock
def test_http_request_post_sends_form_data():
    respx.post("http://example.com/submit").mock(
        return_value=httpx.Response(200, text="ok")
    )
    handler = _handler()

    result = _run(
        handler.handle(
            "http_request",
            {"url": "http://example.com/submit", "method": "POST", "data": {"a": "1"}},
        )
    )

    assert result["status_code"] == 200
    request = respx.calls[0].request
    assert request.method == "POST"
    assert "a=1" in request.content.decode()


@respx.mock
def test_form_discover_lists_forms():
    html = (
        "<html><body>"
        '<form action="/x.php" method="post">'
        '<input type="text" name="id">'
        '<input type="password" name="pwd">'
        "</form>"
        "</body></html>"
    )
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text=html))
    handler = _handler()

    result = _run(handler.handle("form_discover", {"url": "http://example.com/"}))

    assert result["tool"] == "form_discover"
    assert len(result["forms"]) == 1
    assert result["forms"][0]["action"] == "/x.php"
    assert result["forms"][0]["method"] == "post"
    assert [f["name"] for f in result["forms"][0]["fields"]] == ["id", "pwd"]


@respx.mock
def test_http_header_probe_filters_headers():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            headers={
                "Server": "Apache/2.4.49",
                "X-Powered-By": "PHP/8.1",
                "X-Noise": "drop-me",
            },
            text="ok",
        )
    )
    handler = _handler()

    result = _run(handler.handle("http_header_probe", {"url": "http://example.com/"}))

    assert result["headers"]["server"] == "Apache/2.4.49"
    assert result["headers"]["x-powered-by"] == "PHP/8.1"
    assert "x-noise" not in result["headers"]


@respx.mock
def test_session_login_submits_form_and_reuses_cookie():
    respx.get("http://example.com/login").mock(
        return_value=httpx.Response(200, text=_LOGIN_HTML)
    )
    respx.post("http://example.com/authenticate").mock(
        return_value=httpx.Response(
            200, headers={"Set-Cookie": "session=abc123; Path=/; HttpOnly"}
        )
    )
    respx.get("http://example.com/private").mock(
        return_value=httpx.Response(200, text="secret")
    )
    handler = HttpToolHandler(
        client=ScanHTTPClient(rate_limit=0),
        respect_robots=False,
        login_url="http://example.com/login",
        login_username="operator",
        login_password="hunter2",
    )

    login_result = _run(handler.handle("session_login", {}))
    assert login_result["note"] == "sessão estabelecida"

    _run(handler.handle("http_request", {"url": "http://example.com/private"}))

    private = next(
        c for c in respx.calls if str(c.request.url) == "http://example.com/private"
    )
    assert "session=abc123" in private.request.headers["Cookie"]
    assert "hunter2" not in private.request.headers["Cookie"]


@respx.mock
def test_session_login_without_config_returns_note():
    respx.get("http://example.com/").mock(return_value=httpx.Response(200, text="ok"))
    handler = _handler()

    result = _run(handler.handle("session_login", {"url": "http://example.com/"}))

    assert result["note"] == "login não configurado"


@respx.mock
def test_scanner_tool_requires_url():
    handler = _handler()
    with pytest.raises(ToolExecutionError, match="url"):
        _run(handler.handle("http_request", {}))


@respx.mock
def test_scanner_tool_out_of_scope_blocked(monkeypatch):
    logger = mock.MagicMock()
    monkeypatch.setattr("app.tools.http_tools.logger", logger)
    handler = _handler()
    with pytest.raises(ToolExecutionError, match="authorized scope"):
        _run(handler.handle("http_request", {"url": "http://evil.org/"}))
    assert respx.calls == []
    assert logger.info.called
    assert "tool blocked out of scope" in str(logger.info.call_args)


def test_scanner_tool_kill_switch_blocked():
    handler = _handler()
    activate_kill_switch()
    try:
        with pytest.raises(ToolExecutionError, match="Kill switch"):
            _run(handler.handle("http_request", {"url": "http://example.com/"}))
    finally:
        deactivate_kill_switch()


# ---------------------------------------------------------------------------
# ToolExecutor — branch SCANNER
# ---------------------------------------------------------------------------


class _FakeHandler:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def handle(self, handler: str, params: dict) -> dict:
        self.calls.append((handler, params))
        return {"tool": handler, "ok": True}


def test_executor_routes_scanner_tools_to_handler():
    fake = _FakeHandler()
    executor = ToolExecutor(
        _registry(ToolSpec(name="form_discover", kind=ToolKind.SCANNER, handler="form_discover")),
        http_handler=fake,
    )

    result = _run(executor.execute("form_discover", {"url": "http://example.com/"}))

    assert result == {"tool": "form_discover", "ok": True}
    assert fake.calls == [("form_discover", {"url": "http://example.com/"})]


def test_executor_scanner_falls_back_to_tool_name_as_handler():
    fake = _FakeHandler()
    executor = ToolExecutor(
        _registry(ToolSpec(name="custom", kind=ToolKind.SCANNER)),
        http_handler=fake,
    )

    _run(executor.execute("custom", {"url": "http://example.com/"}))

    assert fake.calls[0][0] == "custom"
