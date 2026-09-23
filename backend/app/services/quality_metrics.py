from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Finding, Run

#: Findings "úteis" = aqueles que o operador NÃO descartou como ruído. A
#: decisão humana é o status: candidate/validated contam como úteis;
#: false_positive/discarded não (M9-P3).
USEFUL_STATUSES = ("candidate", "validated")

#: Severidades que contam como "lead" para tempo-até-primeiro-lead (info fica
#: fora — é pista de superfície, não lead de risco).
_LEAD_SEVERITIES = ("low", "medium", "high", "critical")


def fp_rate(*, false_positive: int, validated: int) -> float | None:
    """Taxa de FP entre findings com decisão humana; None sem denominador."""
    decided = false_positive + validated
    if decided <= 0:
        return None
    return round(false_positive / decided, 4)


def is_useful(status: str | None) -> bool:
    return (status or "") in USEFUL_STATUSES


def time_to_first_lead(started_at: datetime | None, findings: list[Finding]) -> float | None:
    """Segundos entre o início do run e o primeiro lead (severidade >= low)."""
    if started_at is None:
        return None
    lead_times = [
        f.created_at
        for f in findings
        if (f.severity or "").lower() in _LEAD_SEVERITIES and f.created_at is not None
    ]
    if not lead_times:
        return None
    started = _naive(started_at)
    first = min(_naive(t) for t in lead_times)
    return round(max(0.0, (first - started).total_seconds()), 3)


def _naive(value: datetime) -> datetime:
    """Normaliza para datetime naive (UTC), tolerando DB que devolve naive."""
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def cost_per_useful_finding(cost: float, useful_count: int) -> float | None:
    """Custo médio por finding útil; None sem findings úteis."""
    if useful_count <= 0:
        return None
    return round(float(cost) / useful_count, 6)


def _run_cost(run: Run) -> float:
    return float((run.result or {}).get("cost", 0.0) or 0.0)


def _run_tokens(run: Run) -> int:
    return int((run.result or {}).get("tokens_used", 0) or 0)


async def compute_quality_metrics(db: AsyncSession) -> dict[str, Any]:
    """Métricas de negócio globais e por alvo (M9-P3).

    FP rate vem da decisão do operador (status); tempo-até-primeiro-lead e
    custo/tokens por finding útil são calculados por run e agregados.
    """
    findings = list((await db.execute(select(Finding))).scalars().all())
    runs = list((await db.execute(select(Run))).scalars().all())

    status_counter: Counter[str] = Counter(f.status for f in findings)
    false_positive = status_counter.get("false_positive", 0)
    validated = status_counter.get("validated", 0)

    by_target: dict[int, Counter[str]] = defaultdict(Counter)
    for f in findings:
        if f.target_id is not None:
            by_target[f.target_id][f.status] += 1

    def _per_target_metrics() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for target_id, counter in by_target.items():
            fp = counter.get("false_positive", 0)
            val = counter.get("validated", 0)
            rows.append(
                {
                    "target_id": target_id,
                    "fp_rate": fp_rate(false_positive=fp, validated=val),
                    "reviewed_count": fp + val,
                }
            )
        return rows

    findings_by_run: dict[int, list[Finding]] = defaultdict(list)
    for f in findings:
        if f.run_id is not None:
            findings_by_run[f.run_id].append(f)

    lead_times: list[float] = []
    useful_costs: list[float] = []
    useful_tokens: list[float] = []
    for run in runs:
        run_findings = findings_by_run.get(run.id, [])
        lead = time_to_first_lead(run.started_at, run_findings)
        if lead is not None:
            lead_times.append(lead)
        useful = sum(1 for f in run_findings if is_useful(f.status))
        if useful > 0:
            useful_costs.append(_run_cost(run) / useful)
            useful_tokens.append(_run_tokens(run) / useful)

    def _avg(values: list[float]) -> float | None:
        return round(sum(values) / len(values), 3) if values else None

    return {
        "fp_rate": fp_rate(false_positive=false_positive, validated=validated),
        "reviewed_count": false_positive + validated,
        "false_positive_count": false_positive,
        "validated_count": validated,
        "useful_findings": sum(1 for f in findings if is_useful(f.status)),
        "time_to_first_lead_seconds_avg": _avg(lead_times),
        "cost_per_useful_finding_avg": _avg(useful_costs),
        "tokens_per_useful_finding_avg": _avg(useful_tokens),
        "by_target": _per_target_metrics(),
    }
