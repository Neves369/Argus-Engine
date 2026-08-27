from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Decision, Finding
from app.orchestration.state import GraphState


async def persist_run_result(
    db: AsyncSession, run_id: int, target_id: int | None, state: GraphState
) -> None:
    """Materialize decisions and findings from a finished run into the DB."""
    for entry in state.history:
        db.add(
            Decision(
                run_id=run_id,
                agent=str(entry.get("agent", "unknown")),
                action=str(entry.get("action", "unknown")),
                detail={k: v for k, v in entry.items() if k not in ("agent", "action")},
            )
        )

    for item in state.findings:
        db.add(
            Finding(
                run_id=run_id,
                target_id=target_id,
                title=str(item.get("title", "untitled")),
                confidence=float(item.get("confidence", 0.0)),
                status=str(item.get("status", "candidate")),
                description=item.get("description"),
                severity=item.get("severity"),
                meta=item,
            )
        )

    await db.flush()
