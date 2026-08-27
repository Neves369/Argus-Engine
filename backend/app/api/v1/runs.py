from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import get_settings
from app.core.security import is_kill_switch_active, validate_scope
from app.db.models import Run, Target
from app.orchestration.director import Director
from app.orchestration.state import GraphState
from app.schemas.run import RunCreate, RunRead

router = APIRouter(prefix="/runs", tags=["runs"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: DBSession) -> Run:
    if is_kill_switch_active():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Kill switch is active")

    settings = get_settings()
    target_dict = payload.target or {}

    if payload.target_id is not None:
        target = await db.get(Target, payload.target_id)
        if target is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target not found")
        target_dict = {"name": target.name, "url": target.url, "notes": target.notes}

    try:
        validate_scope(target_dict.get("name", ""))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    run = Run(target_id=payload.target_id, status="running", started_at=_utcnow())
    db.add(run)
    await db.commit()
    await db.refresh(run)

    state = GraphState(
        target=target_dict,
        budget_tokens=settings.default_budget_tokens,
        budget_cost=settings.default_budget_cost,
    )

    try:
        final_state = await Director().run(state)
        run.status = "completed"
        run.result = final_state.model_dump()
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = str(exc)
    finally:
        run.finished_at = _utcnow()

    await db.commit()
    await db.refresh(run)
    return run


@router.get("", response_model=list[RunRead])
async def list_runs(db: DBSession) -> list[Run]:
    result = await db.execute(select(Run).order_by(Run.id))
    return list(result.scalars().all())


@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: int, db: DBSession) -> Run:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run
