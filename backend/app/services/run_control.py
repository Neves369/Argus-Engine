from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run
from app.services.run_recovery import recover_stale_runs

ACTIVE_STATUSES = ("running", "pending_review")

_cancel_events: dict[int, asyncio.Event] = {}


class RunLockedError(RuntimeError):
    """Raised when a new run would overlap a currently active run."""


def request_cancel(run_id: int) -> None:
    _cancel_events.setdefault(run_id, asyncio.Event()).set()


def is_cancel_requested(run_id: int) -> bool:
    event = _cancel_events.get(run_id)
    return event is not None and event.is_set()


def clear_cancel(run_id: int) -> None:
    _cancel_events.pop(run_id, None)


async def active_run(db: AsyncSession) -> Run | None:
    result = await db.execute(
        select(Run)
        .where(Run.status.in_(ACTIVE_STATUSES))
        .order_by(Run.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def ensure_no_active_run(db: AsyncSession) -> None:
    # Run órfão (processo anterior morreu) não deve travar o lock: recupera
    # para `failed` (retomável) antes de decidir se há um run realmente ativo.
    await recover_stale_runs(db)
    run = await active_run(db)
    if run is not None:
        raise RunLockedError(
            f"Já existe um run em andamento (#{run.id}, status '{run.status}'). "
            "Aguarde ele concluir ou cancele antes de iniciar outro."
        )