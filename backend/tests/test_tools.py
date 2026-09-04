from __future__ import annotations

import asyncio
import sys

import pytest
import respx
from httpx import Response

from app.tools import ToolExecutionError, ToolExecutor, ToolRegistry, ToolSpec
from app.tools.spec import ToolKind


def _make_registry(*specs: ToolSpec) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


def test_registry_authorize():
    echo = ToolSpec(name="echo", kind=ToolKind.CLI, command="echo")
    assert ToolRegistry.authorize(echo, ("echo",)) is True
    assert ToolRegistry.authorize(echo, ("*",)) is True
    assert ToolRegistry.authorize(echo, ()) is False
    assert ToolRegistry.authorize(echo, ("fetch",)) is False


def test_unknown_tool_raises():
    registry = _make_registry()
    with pytest.raises(KeyError):
        registry.get_tool("nope")


def test_cli_execution():
    spec = ToolSpec(name="py", kind=ToolKind.CLI, command=sys.executable, timeout=10.0)
    registry = _make_registry(spec)

    async def _run() -> dict:
        executor = ToolExecutor(registry)
        return await executor.execute("py", {"args": ["-c", "print('ok')"]})

    result = asyncio.run(_run())
    assert result["stdout"] == "ok"
    assert result["returncode"] == 0


@respx.mock
def test_http_execution():
    spec = ToolSpec(
        name="fetch",
        kind=ToolKind.HTTP,
        url="https://example.com/data",
        method="GET",
        timeout=10.0,
    )
    registry = _make_registry(spec)
    respx.get("https://example.com/data").mock(return_value=Response(200, text="body"))

    async def _run() -> dict:
        executor = ToolExecutor(registry)
        return await executor.execute("fetch")

    result = asyncio.run(_run())
    assert result["status_code"] == 200
    assert result["body"] == "body"


def test_destructive_requires_devil_mode():
    spec = ToolSpec(name="danger", kind=ToolKind.CLI, command=sys.executable, destructive=True)
    registry = _make_registry(spec)

    async def _run_off() -> None:
        executor = ToolExecutor(registry)
        with pytest.raises(ToolExecutionError):
            await executor.execute("danger", {"args": ["-c", "print('x')"]})

    asyncio.run(_run_off())

    async def _run_on() -> dict:
        executor = ToolExecutor(registry)
        return await executor.execute("danger", {"args": ["-c", "print('ok')"]}, devil_mode=True)

    result = asyncio.run(_run_on())
    assert result["stdout"] == "ok"


def test_rate_limit_exceeded():
    spec = ToolSpec(
        name="fast",
        kind=ToolKind.CLI,
        command=sys.executable,
        rate_limit=1.0,
        timeout=10.0,
    )
    registry = _make_registry(spec)

    async def _run() -> None:
        executor = ToolExecutor(registry)
        await executor.execute("fast", {"args": ["-c", "pass"]})
        with pytest.raises(ToolExecutionError):
            await executor.execute("fast", {"args": ["-c", "pass"]})

    asyncio.run(_run())


def test_list_tools_endpoint(client):
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    names = {tool["name"] for tool in response.json()}
    assert {"echo", "fetch", "dangerous"} <= names


def test_invoke_denied_for_archetype(client):
    response = client.post("/api/v1/tools/echo/invoke", json={"params": {}, "agent": "justice"})
    assert response.status_code == 403


def test_invoke_unknown_archetype(client):
    response = client.post("/api/v1/tools/echo/invoke", json={"params": {}, "agent": "nope"})
    assert response.status_code == 422


def test_invoke_destructive_blocked_without_devil(client):
    response = client.post("/api/v1/tools/dangerous/invoke", json={"params": {}})
    assert response.status_code == 403


def test_invoke_unknown_tool(client):
    response = client.post("/api/v1/tools/nope/invoke", json={"params": {}})
    assert response.status_code == 404
