from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete

from app.db.models import Finding, Run
from app.db.session import async_session_factory
from app.services.quality_metrics import (
    compute_quality_metrics,
    cost_per_useful_finding,
    fp_rate,
    is_useful,
    time_to_first_lead,
)


def test_fp_rate_operator_decision():
    assert fp_rate(false_positive=2, validated=4) == round(2 / 6, 4)
    assert fp_rate(false_positive=0, validated=0) is None


def test_is_useful():
    assert is_useful("candidate") is True
    assert is_useful("validated") is True
    assert is_useful("false_positive") is False
    assert is_useful("discarded") is False
    assert is_useful(None) is False


def test_time_to_first_lead_uses_low_plus_severity():
    started = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    info = Finding(severity="info", status="candidate")
    info.created_at = started + timedelta(seconds=5)
    lead = Finding(severity="low", status="candidate")
    lead.created_at = started + timedelta(seconds=30)
    assert time_to_first_lead(started, [info, lead]) == 30.0


def test_time_to_first_lead_none_without_lead():
    started = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)
    info = Finding(severity="info", status="candidate")
    info.created_at = started + timedelta(seconds=5)
    assert time_to_first_lead(started, [info]) is None
    assert time_to_first_lead(None, [info]) is None


def test_cost_per_useful_finding():
    assert cost_per_useful_finding(10.0, 4) == 2.5
    assert cost_per_useful_finding(10.0, 0) is None


def test_compute_quality_metrics_aggregates(client):
    async def _run():
        async with async_session_factory() as db:
            await db.execute(delete(Finding))
            await db.execute(delete(Run))
            await db.commit()
            run = Run(
                status="completed",
                started_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC),
                result={"cost": 20.0, "tokens_used": 200},
            )
            db.add(run)
            await db.flush()
            now = datetime(2026, 1, 1, 0, 0, 30, tzinfo=UTC)
            db.add_all(
                [
                    Finding(
                        run_id=run.id,
                        target_id=1,
                        title="a",
                        status="false_positive",
                        severity="low",
                        created_at=now,
                    ),
                    Finding(
                        run_id=run.id,
                        target_id=1,
                        title="b",
                        status="false_positive",
                        severity="low",
                        created_at=now,
                    ),
                    Finding(
                        run_id=run.id,
                        target_id=1,
                        title="c",
                        status="validated",
                        severity="high",
                        created_at=now,
                    ),
                    Finding(
                        run_id=run.id,
                        target_id=1,
                        title="d",
                        status="candidate",
                        severity="info",
                        created_at=now,
                    ),
                ]
            )
            await db.commit()
            return await compute_quality_metrics(db)

    metrics = asyncio.run(_run())
    assert metrics["fp_rate"] == round(2 / 3, 4)
    assert metrics["reviewed_count"] == 3
    assert metrics["false_positive_count"] == 2
    assert metrics["validated_count"] == 1
    # úteis = candidate + validated = 2
    assert metrics["useful_findings"] == 2
    assert metrics["cost_per_useful_finding_avg"] == 10.0
    assert metrics["tokens_per_useful_finding_avg"] == 100.0
    assert metrics["time_to_first_lead_seconds_avg"] == 30.0
