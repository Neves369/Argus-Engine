from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import get_settings
from app.core.security import is_kill_switch_active, validate_scope
from app.db.models import Decision, Finding, Run, Target
from app.db.models import Session as SessionModel
from app.orchestration.compose import validate_sequence
from app.orchestration.director import Director
from app.orchestration.hitl import is_awaiting_review
from app.orchestration.state import GraphState
from app.schemas.decision import DecisionRead
from app.schemas.finding import FindingRead
from app.schemas.review import ReviewCreate
from app.schemas.run import RunCreate, RunRead
from app.services.persistence import persist_run_result
from app.services.run_control import (
    RunLockedError,
    active_run,
    clear_cancel,
    ensure_no_active_run,
    is_cancel_requested,
    request_cancel,
)
from app.services.run_executor import execute_run, resume_run
from app.sources.service import build_sources_service

router = APIRouter(prefix="/runs", tags=["runs"])


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def _guard_no_active_run(db: DBSession) -> None:
    try:
        await ensure_no_active_run(db)
    except RunLockedError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("", response_model=RunRead, status_code=status.HTTP_201_CREATED)
async def create_run(payload: RunCreate, db: DBSession) -> Run:
    if is_kill_switch_active():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Kill switch is active")

    await _guard_no_active_run(db)

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

    archetypes = payload.archetypes
    if archetypes is not None:
        try:
            validate_sequence(archetypes)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    run = Run(target_id=payload.target_id, status="running", started_at=_utcnow())
    db.add(run)
    await db.commit()
    await db.refresh(run)

    state = GraphState(
        target=target_dict,
        budget_tokens=settings.default_budget_tokens,
        budget_cost=settings.default_budget_cost,
        devil_mode=payload.devil_mode,
    )
    state.set_sources_service(build_sources_service())

    try:
        await execute_run(
            db, run, payload.target_id, state, archetypes, build_sources_service()
        )
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


@router.get("/stream")
async def stream_run(
    db: DBSession,
    target: str | None = None,
    session_id: int | None = None,
    devil_mode: bool = False,
    archetypes: list[str] | None = None,
):
    if is_kill_switch_active():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Kill switch is active")

    await _guard_no_active_run(db)

    settings = get_settings()
    session: SessionModel | None = None
    target_meta: dict[str, Any] = {"name": target or ""}

    if session_id is not None:
        session = await db.get(SessionModel, session_id)
        if session is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found")
        cfg = session.config or {}
        if archetypes is None:
            archetypes = cfg.get("archetypes") or None
        target_meta = cfg.get("target") or {}
        devil_mode = bool(cfg.get("devil_mode", devil_mode))

    target_name = str(target_meta.get("name") or "")
    if not target_name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Informe 'target' ou um 'session_id' com alvo definido",
        )

    try:
        validate_scope(target_name)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if archetypes is not None:
        try:
            validate_sequence(archetypes)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    run = Run(status="running", started_at=_utcnow())
    if session is not None:
        run.session_id = session.id
        if session.target_id is not None:
            run.target_id = session.target_id
        else:
            new_target = Target(
                name=target_name,
                url=target_meta.get("url"),
                notes=target_meta.get("notes"),
            )
            db.add(new_target)
            await db.flush()
            session.target_id = new_target.id
            run.target_id = new_target.id
    db.add(run)
    await db.commit()
    await db.refresh(run)
    run_id = run.id

    async def event_stream():
        yield f"event: start\ndata: {json.dumps({'run_id': run_id})}\n\n"
        state = GraphState(
            target=target_meta,
            budget_tokens=settings.default_budget_tokens,
            budget_cost=settings.default_budget_cost,
            devil_mode=devil_mode,
        )
        state.set_sources_service(build_sources_service())
        director = Director(archetypes, sources_service=build_sources_service())
        final = state.model_dump()
        try:
            async for chunk in director.stream(state):
                if is_cancel_requested(run_id):
                    run.status = "cancelled"
                    run.result = final
                    break
                for node, update in chunk.items():
                    final.update(update)
                    yield (
                        "event: node\n"
                        f"data: {json.dumps({'node': node, 'update': update}, default=str)}\n\n"
                    )
            else:
                final_state = GraphState.model_validate(final)
                if is_awaiting_review(final_state):
                    run.status = "pending_review"
                else:
                    run.status = "completed"
                    await persist_run_result(db, run_id, run.target_id, final_state)
                run.result = final
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
        finally:
            clear_cancel(run_id)
            run.finished_at = _utcnow()

        await db.commit()
        yield f"event: done\ndata: {json.dumps({'run_id': run_id, 'status': run.status})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/active")
async def get_active_run(db: DBSession) -> dict[str, Any]:
    run = await active_run(db)
    if run is None:
        return {"active": False, "run_id": None, "status": None}
    return {"active": True, "run_id": run.id, "status": run.status}


@router.post("/{run_id}/cancel")
async def cancel_run(run_id: int, db: DBSession) -> dict[str, Any]:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if run.status != "running":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run #{run_id} não está em execução (status '{run.status}')",
        )
    request_cancel(run_id)
    run.status = "cancelled"
    run.finished_at = _utcnow()
    await db.commit()
    await db.refresh(run)
    return {"status": "ok", "run_id": run_id, "run_status": run.status}


@router.get("/{run_id}", response_model=RunRead)
async def get_run(run_id: int, db: DBSession) -> Run:
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


@router.get("/{run_id}/findings", response_model=list[FindingRead])
async def list_run_findings(run_id: int, db: DBSession) -> list[Finding]:
    result = await db.execute(
        select(Finding).where(Finding.run_id == run_id).order_by(Finding.id)
    )
    return list(result.scalars().all())


@router.get("/{run_id}/decisions", response_model=list[DecisionRead])
async def list_run_decisions(run_id: int, db: DBSession) -> list[Decision]:
    result = await db.execute(
        select(Decision).where(Decision.run_id == run_id).order_by(Decision.id)
    )
    return list(result.scalars().all())


@router.get("/{run_id}/trace")
async def get_run_trace(run_id: int, db: DBSession):
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    trace = (run.result or {}).get("trace") or []
    return {"run_id": run_id, "trace": trace}


@router.post("/{run_id}/review", response_model=RunRead)
async def review_run(run_id: int, payload: ReviewCreate, db: DBSession) -> Run:
    """Answer a pending human-in-the-loop review and resume the run."""
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    decision = {
        "id": payload.approval_id,
        "approved": payload.approved,
        "note": payload.note,
    }
    try:
        await resume_run(db, run, decision)
    except ValueError as exc:
        if "mismatch" in str(exc):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    await db.refresh(run)
    return run


@router.get("/{run_id}/report")
async def report_run(run_id: int, db: DBSession):
    """Structured security report: what was found, severity, exploits, remediation."""
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    result = await db.execute(
        select(Finding).where(Finding.run_id == run_id).order_by(Finding.id)
    )
    findings = list(result.scalars().all())
    from app.services.export import run_report

    return run_report(run, findings)


@router.get("/{run_id}/export")
async def export_run(run_id: int, db: DBSession, format: str = "json"):
    run = await db.get(Run, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")

    result = await db.execute(
        select(Finding).where(Finding.run_id == run_id).order_by(Finding.id)
    )
    findings = list(result.scalars().all())

    if format == "sarif":
        from app.services.export import run_findings_sarif

        return PlainTextResponse(run_findings_sarif(run, findings))

    if format == "json":
        return JSONResponse(
            content=[FindingRead.model_validate(f).model_dump(mode="json") for f in findings]
        )

    if format == "markdown":
        from app.services.export import run_report_markdown

        return PlainTextResponse(run_report_markdown(run, findings))

    if format == "csv":
        from app.services.export import run_findings_csv

        return PlainTextResponse(run_findings_csv(findings))

    raise HTTPException(
        status_code=400, detail="format must be 'sarif', 'json', 'markdown' or 'csv'"
    )
