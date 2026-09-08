from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.db.migrate import upgrade_sync
from app.db.models import Run
from app.db.session import async_session_factory
from app.services.run_control import RunLockedError, ensure_no_active_run
from app.services.run_recovery import recover_stale_runs

_INSTANT = datetime.now(UTC)


@pytest.fixture(scope="module", autouse=True)
def _schema() -> None:
    upgrade_sync("head")


def _create_run(status: str, started_at_offset_hours: int) -> int:
    async def _create() -> int:
        async with async_session_factory() as session:
            run = Run(
                status=status,
                started_at=_INSTANT - timedelta(hours=started_at_offset_hours),
            )
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run.id

    return asyncio.run(_create())


def _status(run_id: int) -> tuple[str, str | None]:
    async def _fetch() -> tuple[str, str | None]:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            return run.status, run.error

    return asyncio.run(_fetch())


def test_recover_marks_stale_running_and_pending_review() -> None:
    running_id = _create_run("running", 48)
    pending_id = _create_run("pending_review", 72)

    async def _run() -> list[int]:
        async with async_session_factory() as session:
            return await recover_stale_runs(session)

    recovered = asyncio.run(_run())
    assert set(recovered) == {running_id, pending_id}

    status, error = _status(running_id)
    assert status == "failed"
    assert "ó" in (error or "")
    assert _status(pending_id)[0] == "failed"


def test_recover_leaves_recent_and_inactive_runs_untouched() -> None:
    recent_id = _create_run("running", 1)
    completed_id = _create_run("completed", 96)
    failed_id = _create_run("failed", 96)
    cancelled_id = _create_run("cancelled", 96)

    async def _run() -> list[int]:
        async with async_session_factory() as session:
            return await recover_stale_runs(session)

    assert asyncio.run(_run()) == []
    assert _status(recent_id)[0] == "running"
    assert _status(completed_id)[0] == "completed"
    assert _status(failed_id)[0] == "failed"
    assert _status(cancelled_id)[0] == "cancelled"


def test_ensure_no_active_run_recovers_stale_run() -> None:
    stale_id = _create_run("running", 48)

    async def _guard() -> None:
        async with async_session_factory() as session:
            await ensure_no_active_run(session)

    asyncio.run(_guard())
    assert _status(stale_id)[0] == "failed"


def test_ensure_no_active_run_still_blocks_recent_run() -> None:
    _create_run("running", 1)

    async def _guard() -> None:
        async with async_session_factory() as session:
            await ensure_no_active_run(session)

    try:
        asyncio.run(_guard())
    except RunLockedError:
        pass
    else:  # pragma: no cover
        raise AssertionError("esperado RunLockedError para run recente ativo")