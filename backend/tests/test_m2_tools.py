from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.scanning.client import ScanHTTPClient
from app.tools import ToolExecutionError, ToolExecutor, ToolRegistry
from app.tools.builtins import BuiltinToolError, BuiltinTools
from app.tools.spec import ToolKind, ToolSpec


def _run(coro):
    return asyncio.run(coro)


def _builtin_registry(*names: str) -> ToolRegistry:
    registry = ToolRegistry()
    for name in names:
        registry.register(
            ToolSpec(
                name=name,
                kind=ToolKind.BUILTIN,
                handler=name,
                timeout=10.0,
                rate_limit=0.0,
                destructive=False,
            )
        )
    return registry


def test_http_request_out_of_scope_blocked():
    registry = _builtin_registry("http_request")
    executor = ToolExecutor(registry)

    async def _run_blocked() -> None:
        with pytest.raises(ToolExecutionError, match="Out of scope"):
            await executor.execute("http_request", {"url": "http://evil.org/"})

    _run(_run_blocked())


@respx.mock
def test_session_login_returns_names_only_and_jar_is_per_executor():
    respx.get("http://example.com/login").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<html><form method="post" action="/do">'
                '<input type="text" name="user">'
                '<input type="password" name="pass">'
                "</form></html>"
            ),
        )
    )
    respx.post("http://example.com/do").mock(
        return_value=httpx.Response(
            200,
            headers={"Set-Cookie": "session=supersecret; Path=/; HttpOnly"},
            text="<html>ok</html>",
        )
    )

    jar = ScanHTTPClient(rate_limit=0)
    builtins = BuiltinTools(client=jar)

    out = _run(
        builtins.run(
            "session_login",
            {"login_url": "http://example.com/login", "username": "admin", "password": "hunter2"},
        )
    )

    assert out["ok"] is True
    assert out["auth_status"] == "success"
    assert out["auth_cookie_names"] == ["session"]
    assert jar.session_cookie_names("example.com") == ["session"]

    segunda_jar = ScanHTTPClient(rate_limit=0)
    segundo = BuiltinTools(client=segunda_jar)
    assert segundo.client.session_cookie_names("example.com") == [], (
        "jar por executor: sessão não vaza entre runs"
    )


@respx.mock
def test_form_discover_reports_sensitive_field_names():
    respx.get("http://example.com/").mock(
        return_value=httpx.Response(
            200,
            text=(
                '<html><form method="POST" action="/submit">'
                '<input type="text" name="cpf">'
                '<input type="password" name="senha">'
                '<input type="file" name="doc">'
                "</form></html>"
            ),
        )
    )
    builtins = BuiltinTools(client=ScanHTTPClient(rate_limit=0))

    out = _run(builtins.run("form_discover", {"url": "http://example.com/"}))

    assert out["ok"] is True
    assert out["form_count"] == 1
    form = out["forms"][0]
    assert form["method"] == "POST"
    assert form["fields"] == ["cpf", "senha", "doc"]
    assert form["sensitive_field_names"] == ["senha", "doc"]


def test_header_reprobe_requires_url():
    builtins = BuiltinTools(client=ScanHTTPClient(rate_limit=0))

    async def _run_empty() -> None:
        with pytest.raises(BuiltinToolError, match="requires a target url"):
            await builtins.run("header_reprobe", {})

    _run(_run_empty())