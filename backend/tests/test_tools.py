from __future__ import annotations

import asyncio
import shutil
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


def _manifest_registry() -> ToolRegistry:
    from app.core.config import get_settings

    registry = ToolRegistry()
    registry.load(get_settings().tools_manifest)
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


def test_manifest_registers_whois_and_dig():
    registry = _manifest_registry()
    for name in ("whois", "dig"):
        spec = registry.get_tool(name)
        assert spec.kind == ToolKind.CLI
        assert spec.destructive is False
        assert spec.sandbox_network is True
        assert spec.timeout > 0
        assert spec.rate_limit > 0


def test_list_tools_includes_whois_and_dig(client):
    response = client.get("/api/v1/tools")
    assert response.status_code == 200
    tools = {tool["name"]: tool for tool in response.json()}
    assert {"whois", "dig"} <= tools.keys()
    assert tools["whois"]["kind"] == "cli"
    assert tools["whois"]["destructive"] is False
    assert tools["dig"]["destructive"] is False


def test_whois_invoke_outside_scope_blocked(client):
    response = client.post(
        "/api/v1/tools/whois/invoke",
        json={"params": {}, "target": "example.org"},
    )
    assert response.status_code == 403


def test_whois_invoke_denied_for_archetype(client):
    response = client.post(
        "/api/v1/tools/whois/invoke",
        json={"params": {}, "target": "sub.example.com", "agent": "justice"},
    )
    assert response.status_code == 403


def test_build_command_bare_target_value():
    spec = ToolSpec(name="whois", kind=ToolKind.CLI, command="whois")
    assert ToolExecutor._build_command(spec, {"target": "example.com"}) == [
        "whois",
        "example.com",
    ]
    assert ToolExecutor._build_command(spec, {"args": ["-h", "whois.iana.org", "example.com"]}) == [
        "whois",
        "-h",
        "whois.iana.org",
        "example.com",
    ]


def test_cli_command_missing_binary_degrades_to_tool_error():
    spec = ToolSpec(name="ghost", kind=ToolKind.CLI, command="/no/such/binary-argus", timeout=5.0)
    registry = _make_registry(spec)

    async def _run() -> None:
        executor = ToolExecutor(registry)
        with pytest.raises(ToolExecutionError, match="command not found"):
            await executor.execute("ghost", {"target": "example.com"})

    asyncio.run(_run())


def test_whois_dig_real_smoke():
    """Best-effort: executa whois/dig reais se os binários existirem e a rede abrir.

    Não é hermético por natureza (recon passivo real). Ausência do binário,
    egress bloqueado ou porta 43/DNS inacessíveis => skip, não falha falsa.
    """
    registry = _manifest_registry()

    for name in ("whois", "dig"):
        if shutil.which(name) is None:
            pytest.skip(f"{name} não instalado neste host")
        executor = ToolExecutor(registry)
        try:
            result = asyncio.run(executor.execute(name, {"target": "example.com"}))
        except ToolExecutionError:
            pytest.skip(f"{name}: egress bloqueado / timeout neste host")
        if result["returncode"] != 0:
            pytest.skip(f"{name}: rede fechada neste host (rc={result['returncode']})")
        assert result["tool"] == name
        assert result["stdout"].strip()
        assert result["stderr_truncated"] is False


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
