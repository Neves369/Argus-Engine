from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import logging
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.llm.compress import compact_tool_output
from app.tools.registry import ToolRegistry
from app.tools.spec import ToolKind, ToolSpec

try:
    import resource  # POSIX only
except ImportError:  # pragma: no cover - non-POSIX platforms (e.g. Windows)
    resource = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


class ToolExecutionError(RuntimeError):
    """Raised when a tool invocation fails or is blocked."""


def _apply_subprocess_limits(memory_mb: int) -> None:
    """``preexec_fn`` for the tool subprocess: cap address space and open files.

    Runs in the forked child before ``exec``, so a failure here must never
    raise — worst case the limit silently doesn't apply, which is strictly
    safer than crashing the whole invocation. POSIX-only; a no-op on
    platforms without the ``resource`` module (e.g. Windows).
    """
    if resource is None:
        return
    mem_bytes = memory_mb * 1024 * 1024
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
    with contextlib.suppress(ValueError, OSError):
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))


def _compact_json_body(text: str) -> str:
    """If `text` is JSON, strip structural noise and re-serialize minified.

    Falls back to whitespace-trimmed plain text when it isn't valid JSON —
    never raises on non-JSON tool output.
    """
    try:
        parsed = json.loads(text)
    except (ValueError, TypeError):
        return " ".join(text.split())
    compacted = compact_tool_output(parsed)
    return json.dumps(compacted, separators=(",", ":"), ensure_ascii=False)


def _truncate_output(data: bytes, max_bytes: int) -> tuple[str, bool]:
    """Decode and cap output length; report whether truncation happened.

    Caps runaway tool output (e.g. an accidental infinite-loop print) from
    bloating memory, logs, and the history entry it ends up in.
    """
    text = data.decode(errors="replace").strip()
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text, False
    return encoded[:max_bytes].decode(errors="ignore") + "...[truncated]", True


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
        if get_settings().tool_output_compression:
            result = compact_tool_output(result)
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
        result = {"tool": tool.name, "status_code": response.status_code, "body": response.text}
        if get_settings().tool_output_compression:
            result["body"] = _compact_json_body(response.text)
        return result

    async def _execute_cli(self, tool: ToolSpec, params: dict[str, Any]) -> dict[str, Any]:
        if not tool.command:
            raise ToolExecutionError(f"CLI tool {tool.name} has no command configured")

        if "args" in params:
            args = [str(a) for a in params["args"]]
        else:
            args = [str(v) for v in params.values()]
        cmd = [tool.command, *args]

        settings = get_settings()
        preexec_fn = (
            functools.partial(
                _apply_subprocess_limits, settings.tool_subprocess_memory_limit_mb
            )
            if resource is not None
            else None
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            preexec_fn=preexec_fn,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=tool.timeout)
        except TimeoutError as exc:
            # asyncio.wait_for cancels *our wait*, not the child — without an
            # explicit kill the process keeps running (and consuming
            # resources) in the background after we've already reported it
            # as failed.
            process.kill()
            with contextlib.suppress(ProcessLookupError):
                await process.wait()
            raise ToolExecutionError(f"Tool {tool.name} timed out") from exc

        max_output = settings.tool_subprocess_max_output_bytes
        stdout_text, stdout_truncated = _truncate_output(stdout, max_output)
        stderr_text, stderr_truncated = _truncate_output(stderr, max_output)

        return {
            "tool": tool.name,
            "returncode": process.returncode,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "stdout_truncated": stdout_truncated,
            "stderr_truncated": stderr_truncated,
        }
