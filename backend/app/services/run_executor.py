from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run
from app.orchestration.director import Director
from app.orchestration.hitl import is_awaiting_review
from app.orchestration.state import GraphState
from app.services.persistence import persist_run_result
from app.sources.service import build_sources_service


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def execute_run(
    db: AsyncSession,
    run: Run,
    target_id: int | None,
    state: GraphState,
    archetypes: list[str] | None,
    sources_service: Any,
) -> GraphState:
    """Execute a graph run, finalizing it or halting for a human decision."""
    director = Director(archetypes, sources_service=sources_service)
    final = await director.run(state)
    if is_awaiting_review(final):
        run.status = "pending_review"
        run.result = final.model_dump()
    else:
        run.status = "completed"
        run.result = final.model_dump()
        await persist_run_result(db, run.id, target_id, final)
    return final


async def resume_run(
    db: AsyncSession,
    run: Run,
    decision: dict[str, Any],
    *,
    sources_service: Any | None = None,
) -> GraphState:
    """Apply a human decision to a pending review and resume the run.

    Raises ``ValueError`` with a user-facing message when the run is not
    awaiting the supplied approval.
    """
    if run.status != "pending_review" or not run.result:
        raise ValueError("Run is not awaiting review")

    saved = run.result
    pending = saved.get("pending_review")
    if not pending:
        raise ValueError("Run has no pending review")
    if str(pending.get("id")) != str(decision.get("id")):
        raise ValueError("approval_id mismatch")

    state = GraphState.model_validate(saved)
    state.set_sources_service(sources_service or build_sources_service())
    state.human_decision = decision

    director = Director(
        archetypes=None, sources_service=sources_service or build_sources_service()
    )
    final = await director.run_from(state, state.next_agent or "emperor")
    if is_awaiting_review(final):
        run.status = "pending_review"
    else:
        run.status = "completed"
        await persist_run_result(db, run.id, run.target_id, final)
    run.result = final.model_dump()
    run.finished_at = _utcnow()
    await db.commit()
    return final
