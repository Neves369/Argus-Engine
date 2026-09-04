from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentRun, Decision, Finding
from app.db.models.finding import FindingStatus
from app.orchestration.state import GraphState


def _iso_to_dt(value) -> object | None:
    """Coerce an ISO-8601 string from the trace back to a datetime for storage."""
    if not value:
        return None
    try:
        from datetime import datetime

        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_float(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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

    for step in state.trace:
        db.add(
            AgentRun(
                run_id=run_id,
                archetype=str(step.get("node", "unknown")),
                action=step.get("action"),
                tokens=int(step.get("tokens", 0)),
                cost=float(step.get("cost", 0.0)),
                started_at=_iso_to_dt(step.get("started_at")),
                finished_at=_iso_to_dt(step.get("finished_at")),
                detail=step,
            )
        )

    for item in state.findings:
        status = str(item.get("status", "candidate"))
        # `requires_human_review` is metadata surfaced to the operator (the
        # finding stays "candidate" either way — the existing async review
        # lifecycle, /findings/{id}/validate and PATCH .../status, is how a
        # human actually clears it). Only an EXPLICIT rejection — recorded
        # via a "finding_review" HITL gate, for any archetype that requests
        # one through `_request_approval` — discards it automatically here;
        # the mere absence of a verdict must never silently discard a
        # finding before a human had any chance to see it.
        if item.get("requires_human_review") and status == FindingStatus.CANDIDATE.value:
            verdict = verdict_by_finding.get(str(item.get("id")))
            if verdict == "rejected":
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
                category=item.get("category"),
                affected=item.get("affected"),
                cvss_score=_as_float(item.get("cvss_score")),
                cvss_vector=item.get("cvss_vector"),
                cves=item.get("cves"),
                known_exploits=item.get("known_exploits"),
                remediation=item.get("remediation"),
                references=item.get("references"),
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
