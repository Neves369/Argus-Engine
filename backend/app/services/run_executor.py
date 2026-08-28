from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run
from app.orchestration.director import Director
from app.orchestration.hitl import is_awaiting_review
from app.orchestration.state import GraphState
from app.services.persistence import persist_run_result


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
