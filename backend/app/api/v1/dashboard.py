from __future__ import annotations

from collections import Counter, defaultdict

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DBSession
from app.db.models import AgentRun, Finding, Run

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary")
async def dashboard_summary(db: DBSession):
    """Aggregate counts, costs and pending reviews across all runs."""
    run_rows = (await db.execute(select(Run))).scalars().all()

    statuses: Counter[str] = Counter()
    total_cost: float = 0.0
    total_tokens: int = 0
    pending_reviews = 0
    for run in run_rows:
        statuses[run.status] += 1
        result = run.result or {}
        total_cost += float(result.get("cost", 0.0))
        total_tokens += int(result.get("tokens_used", 0))
        if run.status == "pending_review":
            pending_reviews += 1

    finding_rows = (await db.execute(select(Finding))).scalars().all()
    severities: Counter[str] = Counter()
    finding_statuses: Counter[str] = Counter()
    for finding in finding_rows:
        severities[finding.severity or "unknown"] += 1
        finding_statuses[finding.status] += 1

    trace_rows = (await db.execute(select(AgentRun))).scalars().all()
    trace_tokens = int(sum(int(t.tokens) for t in trace_rows))
    trace_cost = round(sum(float(t.cost) for t in trace_rows), 6)

    return {
        "runs": {"total": len(run_rows), "by_status": dict(statuses)},
        "pending_reviews": pending_reviews,
        "findings": {
            "total": len(finding_rows),
            "by_severity": dict(severities),
            "by_status": dict(finding_statuses),
        },
        "costs": {
            "total_cost": round(total_cost, 6),
            "total_tokens": total_tokens,
            "trace_tokens": trace_tokens,
            "trace_cost": trace_cost,
        },
    }


@router.get("/runs")
async def dashboard_runs(db: DBSession):
    """List runs with summary metrics for the dashboard table."""
    run_rows = (await db.execute(select(Run).order_by(Run.id.desc()))).scalars().all()

    finding_counts: dict[int, int] = defaultdict(int)
    severity_by_run: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for run_id, severity in (
        await db.execute(select(Finding.run_id, Finding.severity))
    ).all():
        if run_id is None:
            continue
        finding_counts[run_id] += 1
        key = (severity or "unknown").lower()
        severity_by_run[run_id][key] += 1

    rows = []
    for run in run_rows:
        result = run.result or {}
        row = {
            "id": run.id,
            "status": run.status,
            "target": (result.get("target") or {}).get("name"),
            "findings": finding_counts.get(run.id, 0),
            "by_severity": dict(severity_by_run.get(run.id, {})),
            "cost": round(float(result.get("cost", 0.0)), 6),
            "tokens": int(result.get("tokens_used", 0)),
            "stop_reason": result.get("stop_reason"),
            "created_at": run.created_at.isoformat() if run.created_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        }
        rows.append(row)
    return rows
