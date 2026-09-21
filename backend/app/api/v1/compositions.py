from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import budget_for_depth, get_settings
from app.core.security import is_kill_switch_active, validate_scope
from app.db.models import Run, Session, Target
from app.orchestration.compose import validate_sequence
from app.orchestration.state import GraphState
from app.probing.engine import build_probe_engine
from app.scanning.service import build_scan_service
from app.scanning.verify import build_verification_service
from app.schemas.composition import CompositionCreate, CompositionExecute, CompositionRead
from app.services.run_control import RunLockedError, ensure_no_active_run
from app.services.run_executor import execute_run
from app.sources.service import build_sources_service
from app.tools.executor import build_tool_executor

router = APIRouter(prefix="/compositions", tags=["compositions"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


@router.post("", response_model=CompositionRead, status_code=status.HTTP_201_CREATED)
async def create_composition(payload: CompositionCreate, db: DBSession) -> Session:
    try:
        validate_sequence(payload.archetypes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    session = Session(
        name=payload.name,
        status="open",
        config={
            "archetypes": payload.archetypes,
            "target": payload.target,
            "devil_mode": payload.devil_mode,
            "depth": payload.depth,
        },
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("", response_model=list[CompositionRead])
async def list_compositions(db: DBSession) -> list[Session]:
    result = await db.execute(select(Session).order_by(Session.id))
    return list(result.scalars().all())


@router.get("/{composition_id}", response_model=CompositionRead)
async def get_composition(composition_id: int, db: DBSession) -> Session:
    session = await db.get(Session, composition_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Composition not found"
        )
    return session


@router.delete("/{composition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_composition(composition_id: int, db: DBSession) -> None:
    session = await db.get(Session, composition_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Composition not found"
        )
    await db.delete(session)
    await db.commit()


@router.post("/{composition_id}/execute")
async def execute_composition(
    composition_id: int, db: DBSession, payload: CompositionExecute | None = None
) -> dict[str, Any]:
    if is_kill_switch_active():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Kill switch is active")

    try:
        await ensure_no_active_run(db)
    except RunLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    session = await db.get(Session, composition_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Composition not found"
        )

    config = session.config or {}
    archetypes = config.get("archetypes", [])
    try:
        validate_sequence(archetypes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    target: dict[str, Any] = config.get("target") or {}
    target_name = str(target.get("name", ""))
    if target_name:
        try:
            validate_scope(target_name)
            target_url = str(target.get("url") or "")
            if target_url.strip():
                validate_scope(target_url)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    target_id = session.target_id
    if target_name and target_id is None:
        new_target = Target(
            name=target_name,
            url=target.get("url"),
            notes=target.get("notes"),
        )
        db.add(new_target)
        await db.flush()
        target_id = new_target.id
        session.target_id = target_id

    settings = get_settings()
    depth = str(config.get("depth") or settings.depth_default)
    if depth not in ("quick", "deep"):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="depth must be 'quick' or 'deep'",
        )
    budget_tokens, budget_cost = budget_for_depth(depth)
    state = GraphState(
        target=target,
        devil_mode=bool(config.get("devil_mode", False)),
        budget_tokens=budget_tokens,
        budget_cost=budget_cost,
        composition=archetypes,
        depth=depth,
    )
    services = (
        build_sources_service(),
        build_scan_service(),
        build_verification_service(),
        build_tool_executor(),
        build_probe_engine(),
    )
    sources, scan, verification, tools, probe_engine = services
    state.set_sources_service(sources)
    state.set_scan_service(scan)
    state.set_verification_service(verification)
    state.set_tool_executor(tools)
    state.set_probe_engine(probe_engine)
    run = Run(target_id=target_id, session_id=session.id, status="running", started_at=_utcnow())
    db.add(run)
    await db.flush()
    run_id = run.id

    try:
        await execute_run(
            db,
            run,
            target_id,
            state,
            archetypes,
            sources,
            scan,
            verification,
            tools,
            probe_engine,
        )
    except Exception as exc:  # noqa: BLE001
        run.status = "failed"
        run.error = str(exc)
    finally:
        run.finished_at = _utcnow()
        session.status = "done"

    await db.commit()
    return {"run_id": run_id, "status": run.status}
