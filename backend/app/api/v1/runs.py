from __future__ import annotations

import json
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from sqlalchemy import select

from app.api.deps import DBSession
from app.core.config import get_settings
from app.core.security import is_kill_switch_active, validate_scope
from app.db.models import Decision, Finding, Run, Target
from app.orchestration.compose import validate_sequence
from app.orchestration.director import Director
from app.orchestration.state import GraphState
from app.schemas.decision import DecisionRead
from app.schemas.finding import FindingRead
from app.schemas.run import RunCreate, RunRead
from app.services.persistence import persist_run_result
from app.sources.service import build_sources_service

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
        final_state = await Director(archetypes).run(state)
        run.status = "completed"
        run.result = final_state.model_dump()
        await persist_run_result(db, run.id, run.target_id, final_state)
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
    target: str,
    db: DBSession,
    devil_mode: bool = False,
    archetypes: list[str] | None = None,
):
    if is_kill_switch_active():
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Kill switch is active")

    try:
        validate_scope(target)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if archetypes is not None:
        try:
            validate_sequence(archetypes)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc

    settings = get_settings()
    run = Run(status="running", started_at=_utcnow())
    db.add(run)
    await db.commit()
    await db.refresh(run)
    run_id = run.id

    async def event_stream():
        state = GraphState(
            target={"name": target},
            budget_tokens=settings.default_budget_tokens,
            budget_cost=settings.default_budget_cost,
            devil_mode=devil_mode,
        )
        state.set_sources_service(build_sources_service())
        final = state.model_dump()
        try:
            async for chunk in Director(archetypes).stream(state):
                for node, update in chunk.items():
                    final.update(update)
                    yield (
                        "event: node\n"
                        f"data: {json.dumps({'node': node, 'update': update}, default=str)}\n\n"
                    )
            run.status = "completed"
            run.result = final
            await persist_run_result(db, run_id, run.target_id, GraphState.model_validate(final))
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
        finally:
            run.finished_at = _utcnow()

        await db.commit()
        yield f"event: done\ndata: {json.dumps({'run_id': run_id, 'status': run.status})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


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


@router.get("/{run_id}/export")
async def export_run(run_id: int, db: DBSession, format: str = "json"):
    result = await db.execute(
        select(Finding).where(Finding.run_id == run_id).order_by(Finding.id)
    )
    findings = list(result.scalars().all())

    if format == "json":
        return JSONResponse(
            content=[FindingRead.model_validate(f).model_dump(mode="json") for f in findings]
        )
    if format == "markdown":
        lines = ["# Findings", ""]
        for finding in findings:
            lines.append(f"## {finding.title}")
            lines.append(f"- status: {finding.status}")
            lines.append(f"- confidence: {finding.confidence}")
            lines.append(f"- severity: {finding.severity or 'n/a'}")
            if finding.description:
                lines.append("")
                lines.append(finding.description)
            lines.append("")
        return PlainTextResponse("\n".join(lines))

    raise HTTPException(status_code=400, detail="format must be 'json' or 'markdown'")
