from __future__ import annotations

import asyncio
import os
import shutil

import pytest

from app.core.config import get_settings
from app.tools import ToolExecutionError, ToolExecutor, ToolRegistry, ToolSpec
from app.tools.spec import ToolKind


def _registry(*specs: ToolSpec) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


class _FakeProcess:
    def __init__(
        self,
        returncode: int,
        stdout: bytes = b"",
        stderr: bytes = b"",
        *,
        hang: bool = False,
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self._hang = hang
        self.killed = False

    async def communicate(self):
        if self._hang:
            await asyncio.sleep(3600)
        return self._stdout, self._stderr

    async def wait(self):
        return

    def kill(self) -> None:
        self.killed = True


class _FakeSubprocessRunner:
    """Records argv of every ``create_subprocess_exec`` call.

    ``await``ed so the executor can hold the coroutine it ``create``ed in the
    same way as the real API; ``results`` is consumed in order, with the last
    entry reused for any extra calls (e.g. the timeout cleanup ``docker rm``).
    """

    def __init__(self, results: list[_FakeProcess]) -> None:
        self._results = results
        self.calls: list[tuple[tuple[str, ...], dict]] = []

    async def __call__(self, *args, **kwargs) -> _FakeProcess:
        self.calls.append((args, kwargs))
        return self._results[min(len(self.calls) - 1, len(self._results) - 1)]


def _run(coro):
    return asyncio.run(coro)


def _enable_sandbox(monkeypatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_sandbox", True)


def _echo_spec(**kwargs) -> ToolSpec:
    defaults: dict = {
        "name": "sb",
        "kind": ToolKind.CLI,
        "command": "echo",
        "timeout": 5.0,
    }
    defaults.update(kwargs)
    return ToolSpec(**defaults)


# ---- decisão sandbox vs subprocesso ----


def test_sandbox_disabled_still_uses_subprocess(monkeypatch):
    monkeypatch.setattr(get_settings(), "tool_sandbox", False)
    runner = _FakeSubprocessRunner([_FakeProcess(0, b"ok")])
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)

    result = _run(ToolExecutor(_registry(_echo_spec())).execute("sb", {"args": ["hi"]}))

    assert result["stdout"] == "ok"
    used_docker = any(args[0] == "docker" for args, _ in runner.calls)
    assert used_docker is False


def test_sandbox_fail_closed_when_docker_binary_missing(monkeypatch):
    _enable_sandbox(monkeypatch)
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    executor = ToolExecutor(_registry(_echo_spec()))

    with pytest.raises(ToolExecutionError, match="docker binary not found"):
        _run(executor.execute("sb", {"args": ["hi"]}))


# ---- execução em container ----


def test_sandbox_runs_docker_with_expected_flags(monkeypatch):
    _enable_sandbox(monkeypatch)
    runner = _FakeSubprocessRunner([_FakeProcess(0, b"hello")])
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)

    result = _run(ToolExecutor(_registry(_echo_spec())).execute("sb", {"args": ["world"]}))

    assert result["stdout"] == "hello"
    assert result["returncode"] == 0
    argv, _ = runner.calls[0]
    argv = list(argv)
    assert argv[0] == "docker" and argv[1] == "run"
    for flag in (
        "--rm",
        "--read-only",
        "--cap-drop",
        "--pids-limit",
        "--cpus",
        "--memory",
        "--memory-swap",
        "--user",
        "--ulimit",
    ):
        assert flag in argv, f"expected docker flag {flag}"
    assert "--network" in argv and "none" in argv
    assert argv[-3] == "alpine:latest"
    assert argv[-2:] == ["echo", "world"]


def test_sandbox_network_override_removes_network_none(monkeypatch):
    _enable_sandbox(monkeypatch)
    runner = _FakeSubprocessRunner([_FakeProcess(0, b"")])
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)
    spec = _echo_spec(sandbox_network=True)

    _run(ToolExecutor(_registry(spec)).execute("sb", {"args": ["x"]}))

    argv = list(runner.calls[0][0])
    assert "--network" not in argv


def test_sandbox_image_override(monkeypatch):
    _enable_sandbox(monkeypatch)
    runner = _FakeSubprocessRunner([_FakeProcess(0, b"")])
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)
    spec = _echo_spec(sandbox_image="python:3.12-alpine")

    _run(ToolExecutor(_registry(spec)).execute("sb", {"args": ["-V"]}))

    argv = list(runner.calls[0][0])
    assert "python:3.12-alpine" in argv


def test_sandbox_fails_closed_on_daemon_error(monkeypatch):
    _enable_sandbox(monkeypatch)
    runner = _FakeSubprocessRunner(
        [_FakeProcess(125, stderr=b"Cannot connect to the Docker daemon")]
    )
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)

    with pytest.raises(ToolExecutionError, match="Sandbox failed to start"):
        _run(ToolExecutor(_registry(_echo_spec())).execute("sb", {"args": ["x"]}))


def test_sandbox_timeout_kills_container(monkeypatch):
    _enable_sandbox(monkeypatch)
    runner = _FakeSubprocessRunner(
        [_FakeProcess(0, hang=True), _FakeProcess(0, hang=True)]
    )
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)
    spec = _echo_spec(timeout=0.1)

    with pytest.raises(ToolExecutionError, match="timed out in sandbox"):
        _run(ToolExecutor(_registry(spec)).execute("sb", {"args": ["x"]}))

    assert runner.calls[0][0][0] == "docker"
    cleanup_argv = list(runner.calls[1][0])
    assert cleanup_argv[:3] == ["docker", "rm", "-f"]
    assert cleanup_argv[3].startswith("argus-sandbox-")


def test_sandbox_truncates_output(monkeypatch):
    _enable_sandbox(monkeypatch)
    monkeypatch.setattr(get_settings(), "tool_subprocess_max_output_bytes", 10)
    runner = _FakeSubprocessRunner([_FakeProcess(0, b"x" * 1000)])
    monkeypatch.setattr("app.tools.executor.asyncio.create_subprocess_exec", runner)

    result = _run(ToolExecutor(_registry(_echo_spec())).execute("sb", {"args": ["x"]}))

    assert result["stdout_truncated"] is True
    assert result["stdout"].endswith("...[truncated]")


@pytest.mark.skipif(
    bool(os.environ.get("ARGUS_TEST_SANDBOX")) is False,
    reason="set ARGUS_TEST_SANDBOX=1 to exercise the real Docker daemon",
)
@pytest.mark.skipif(shutil.which("docker") is None, reason="docker binary not available")
def test_sandbox_real_docker_invocation(monkeypatch):
    _enable_sandbox(monkeypatch)
    spec = _echo_spec()
    result = _run(ToolExecutor(_registry(spec)).execute("sb", {"args": ["hello"]}))
    assert result["returncode"] == 0
    assert result["stdout"].strip() == "hello"