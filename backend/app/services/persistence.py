from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Decision, Finding
from app.db.models.finding import FindingStatus
from app.orchestration.state import GraphState


async def persist_run_result(
    db: AsyncSession, run_id: int, target_id: int | None, state: GraphState
) -> None:
    """Materialize decisions and findings from a finished run into the DB."""
    _persist_human_decisions(db, run_id, state)
    verdict_by_finding = _finding_verdicts(state)

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
        status = str(item.get("status", "candidate"))
        if item.get("requires_human_review"):
            verdict = verdict_by_finding.get(str(item.get("id")))
            if status == FindingStatus.CANDIDATE.value:
                if verdict == "rejected":
                    status = FindingStatus.DISCARDED.value
                elif not verdict:
                    status = FindingStatus.DISCARDED.value
        db.add(
            Finding(
                run_id=run_id,
                target_id=target_id,
                title=str(item.get("title", "untitled")),
                confidence=float(item.get("confidence", 0.0)),
                status=status,
                description=item.get("description"),
                severity=item.get("severity"),
                requires_human_review=bool(item.get("requires_human_review", False)),
                meta=item,
            )
        )

    await db.flush()


def _finding_verdicts(state: GraphState) -> dict[str, str]:
    verdicts: dict[str, str] = {}
    for entry in state.review_log:
        if entry.get("kind") != "finding_review":
            continue
        proposal = entry.get("proposal") or {}
        if proposal.get("id"):
            verdicts[str(proposal["id"])] = str(entry.get("verdict", "rejected"))
    return verdicts


def _persist_human_decisions(
    db: AsyncSession, run_id: int, state: GraphState
) -> None:
    for entry in state.review_log:
        db.add(
            Decision(
                run_id=run_id,
                agent="human",
                action=str(entry.get("verdict", "reviewed")),
                detail=entry,
            )
        )
