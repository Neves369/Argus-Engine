from __future__ import annotations

import asyncio
import time

from app.agents import get_archetype
from app.core.config import get_settings
from app.orchestration.state import GraphState
from app.scanning.service import ScanReport


def _run(coro):
    return asyncio.run(coro)


class _Spec:
    name = "slow"
    target_kind = "any"
    query_param = "q"


class _SlowSources:
    """Fake sources service whose query takes a noticeable time."""

    def __init__(self) -> None:
        self.queried = False

    def available_sources(self) -> list[str]:
        return ["slow"]

    def get_source(self, name: str) -> _Spec:
        return _Spec()

    async def query(self, name: str, params: dict) -> dict:
        await asyncio.sleep(0.2)
        self.queried = True
        return {"status": "ok", "source": name, "data": {"note": "observed"}}


class _SlowScan:
    """Fake scan service whose scan takes a noticeable time."""

    def __init__(self) -> None:
        self.calls = 0

    async def scan(self, target: dict) -> ScanReport:
        await asyncio.sleep(0.2)
        self.calls += 1
        return ScanReport(target=str(target.get("name") or ""))


def _hermit_state(sources, scan) -> GraphState:
    state = GraphState(target={"name": "example.com"})
    state.set_sources_service(sources)
    state.set_scan_service(scan)
    return state


def test_hermit_runs_sources_and_scan_concurrently(monkeypatch):
    sources = _SlowSources()
    scan = _SlowScan()
    state = _hermit_state(sources, scan)

    started = time.monotonic()
    update = _run(get_archetype("hermit").run(state))
    elapsed = time.monotonic() - started

    # Sequential (attempt + 0.2s + 0.2s) would take >= 0.4s; overlapping the
    # two slow legs keeps it near 0.2s — that's the parallelism under test.
    assert sources.queried is True
    assert scan.calls == 1
    assert elapsed < 0.36, f"expected parallel execution, took {elapsed:.2f}s"
    assert update["history"][-1]["scanned"] is True


def test_hermit_stays_sequential_when_lever_off(monkeypatch):
    monkeypatch.setattr(get_settings(), "agent_parallel", False)
    sources = _SlowSources()
    scan = _SlowScan()
    state = _hermit_state(sources, scan)

    started = time.monotonic()
    _run(get_archetype("hermit").run(state))
    elapsed = time.monotonic() - started

    assert elapsed >= 0.36, f"expected sequential execution, took {elapsed:.2f}s"
    assert scan.calls == 1


def test_hermit_semantics_unchanged_by_parallel_flag(monkeypatch):
    """The state update must not depend on which mode ran."""

    def _run_outcome():
        state = _hermit_state(_SlowSources(), _SlowScan())
        return _run(get_archetype("hermit").run(state))

    parallel_update = _run_outcome()
    monkeypatch.setattr(get_settings(), "agent_parallel", False)
    sequential_update = _run_outcome()

    assert parallel_update["history"] == sequential_update["history"]
    assert parallel_update["tokens_used"] == sequential_update["tokens_used"]
    assert parallel_update["confidence"] == sequential_update["confidence"]