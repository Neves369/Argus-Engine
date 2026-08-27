from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import httpx

from app.tools.registry import ToolRegistry
from app.tools.spec import ToolKind, ToolSpec

logger = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when a tool invocation fails or is blocked."""


class ToolExecutor:
    """Executes registered tools with rate limiting, timeouts and mode gating."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._last_invocation: dict[str, float] = {}

    def _check_rate_limit(self, tool: ToolSpec) -> None:
        if tool.rate_limit <= 0:
            return
        last = self._last_invocation.get(tool.name)
        now = time.monotonic()
        if last is not None and (now - last) < (1.0 / tool.rate_limit):
            raise ToolExecutionError(f"Rate limit exceeded for tool {tool.name}")
        self._last_invocation[tool.name] = now

    async def execute(
        self,
        name: str,
        params: dict[str, Any] | None = None,
        *,
        devil_mode: bool = False,
    ) -> dict[str, Any]:
        tool = self._registry.get_tool(name)
        params = params or {}

        if tool.destructive and not devil_mode:
            raise ToolExecutionError(f"Tool {name} is destructive and requires devil_mode")

        self._check_rate_limit(tool)

        started = time.monotonic()
        if tool.kind == ToolKind.HTTP:
            result = await self._execute_http(tool, params)
        elif tool.kind == ToolKind.CLI:
            result = await self._execute_cli(tool, params)
        else:
            raise ToolExecutionError(f"Unknown tool kind: {tool.kind}")

        logger.info(
            "tool invoked",
            extra={
                "tool": name,
                "kind": tool.kind,
                "destructive": tool.destructive,
                "devil_mode": devil_mode,
                "duration_ms": round((time.monotonic() - started) * 1000, 2),
            },
        )
        return result

    async def _execute_http(self, tool: ToolSpec, params: dict[str, Any]) -> dict[str, Any]:
        if not tool.url:
            raise ToolExecutionError(f"HTTP tool {tool.name} has no URL configured")
        async with httpx.AsyncClient(timeout=tool.timeout) as client:
            try:
                if tool.method.upper() == "POST":
                    response = await client.post(tool.url, json=params)
                else:
                    response = await client.get(tool.url, params=params)
            except httpx.HTTPError as exc:
                raise ToolExecutionError(f"Tool {tool.name} request failed: {exc}") from exc

        if response.status_code >= 400:
            raise ToolExecutionError(
                f"Tool {tool.name} returned {response.status_code}: {response.text[:200]}"
            )
        return {"tool": tool.name, "status_code": response.status_code, "body": response.text}

    async def _execute_cli(self, tool: ToolSpec, params: dict[str, Any]) -> dict[str, Any]:
        if not tool.command:
            raise ToolExecutionError(f"CLI tool {tool.name} has no command configured")

        if "args" in params:
            args = [str(a) for a in params["args"]]
        else:
            args = [str(v) for v in params.values()]
        cmd = [tool.command, *args]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=tool.timeout)
        except TimeoutError as exc:
            raise ToolExecutionError(f"Tool {tool.name} timed out") from exc

        return {
            "tool": tool.name,
            "returncode": process.returncode,
            "stdout": stdout.decode(errors="replace").strip(),
            "stderr": stderr.decode(errors="replace").strip(),
        }
