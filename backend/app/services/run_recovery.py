from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run

_STALE_STATUSES = ("running", "pending_review")
_RECOVERY_ERROR = (
    "Run órfão recuperado — o processo anterior terminou sem finalizar este run."
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def recover_stale_runs(db: AsyncSession) -> list[int]:
    """Move active runs abandoned by a dead process to a resumable failure.

    A `running`/`pending_review` run older than `run_stale_after_seconds` is
    considered orphaned: this app is single-process, so no active run can be
    executing inside the current process after a boot or before a lock check.
    Recovery keeps the run's persisted `result` — marking it `failed` (one of
    `RESUMABLE_STATUSES`) lets the operator retake it via the existing resume UI.

    Returns the ids recovered, so callers can log them.
    """
    from app.core.config import get_settings

    cutoff = _utcnow() - timedelta(seconds=get_settings().run_stale_after_seconds)
    result = await db.execute(
        select(Run).where(Run.status.in_(_STALE_STATUSES), Run.started_at < cutoff)
    )
    recovered: list[int] = []
    for run in result.scalars():
        run.status = "failed"
        run.finished_at = _utcnow()
        run.error = _RECOVERY_ERROR
        recovered.append(run.id)
    if recovered:
        await db.commit()
    return recovered