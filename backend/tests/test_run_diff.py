from __future__ import annotations

import asyncio

import pytest

from app.db.models import Finding, Run
from app.db.session import async_session_factory
from app.services.run_diff import compare_runs


async def _seed(db, target_id: int, run_status: str = "completed") -> Run:
    run = Run(target_id=target_id, status=run_status)
    db.add(run)
    await db.flush()
    return run


def _finding(run_id: int, fingerprint: str, severity: str, status: str = "candidate"):
    return Finding(
        run_id=run_id,
        title=f"finding {fingerprint}",
        severity=severity,
        status=status,
        confidence=0.5,
        fingerprint=fingerprint,
    )


def _run_pair(setup) -> dict:
    async def _run():
        async with async_session_factory() as db:
            baseline, current = await setup(db)
            return await compare_runs(db, baseline, current)

    return asyncio.run(_run())


def test_diff_new_resolved_unchanged_changed(client):
    async def _setup(db):
        base = await _seed(db, target_id=1)
        cur = await _seed(db, target_id=1)
        await db.flush()
        db.add_all(
            [
                # baseline only -> resolved
                _finding(base.id, "fp-resolved", "low"),
                # both, same -> unchanged
                _finding(base.id, "fp-same", "high"),
                # both, changed severity -> changed
                _finding(base.id, "fp-changed", "medium"),
            ]
        )
        db.add_all(
            [
                # current only -> new
                _finding(cur.id, "fp-new", "high"),
                _finding(cur.id, "fp-same", "high"),
                _finding(cur.id, "fp-changed", "critical"),
            ]
        )
        await db.commit()
        return base, cur

    result = _run_pair(_setup)
    counts = result["counts"]
    assert counts == {"new": 1, "resolved": 1, "unchanged": 1, "changed": 1}
    assert result["new"][0]["fingerprint"] == "fp-new"
    assert result["resolved"][0]["fingerprint"] == "fp-resolved"
    assert result["unchanged"][0]["fingerprint"] == "fp-same"
    assert result["changed"][0]["current"]["severity"] == "critical"
    assert result["changed"][0]["baseline"]["severity"] == "medium"


def test_diff_rejects_different_targets(client):
    async def _setup(db):
        base = await _seed(db, target_id=1)
        cur = await _seed(db, target_id=2)
        await db.commit()
        return base, cur

    async def _run():
        async with async_session_factory() as db:
            base, cur = await _setup(db)
            with pytest.raises(ValueError):
                await compare_runs(db, base, cur)

    asyncio.run(_run())
