from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import select

from app.db.models import Finding, Run
from app.db.session import async_session_factory
from app.services.fingerprints import finding_fingerprint
from app.services.persistence import persist_run_result


class _State(SimpleNamespace):
    history = []
    trace = []
    review_log = []

    def __init__(self) -> None:
        super().__init__(
            history=[],
            trace=[],
            review_log=[],
            findings=[
                {
                    "id": None,
                    "title": "SQL Injection em login",
                    "description": "d",
                    "severity": "high",
                    "category": "Aplicação / injeção",
                    "affected": "example.com",
                    "cvss_score": None,
                    "cvss_vector": None,
                    "cves": [],
                    "known_exploits": [],
                    "remediation": "r",
                    "references": [],
                    "confidence": 0.7,
                    "status": "candidate",
                    "requires_human_review": True,
                }
            ],
        )


def test_fingerprint_stable_and_normalized():
    a = finding_fingerprint("SQL Injection", "Aplicação / X", "example.com")
    b = finding_fingerprint("  sql injection ", "aplicação / x", "example.com")
    assert a == b
    assert len(a) == 32


def test_fingerprint_differs_on_fields():
    base = finding_fingerprint("t", "c", "a")
    assert base != finding_fingerprint("t2", "c", "a")
    assert base != finding_fingerprint("t", "c2", "a")
    assert base != finding_fingerprint("t", "c", "a2")


def test_persist_run_result_sets_fingerprint(client):
    async def _run():
        async with async_session_factory() as db:
            run = Run(status="completed")
            db.add(run)
            await db.flush()
            await persist_run_result(db, run.id, None, _State())
            await db.commit()
            rows = list(
                (
                    await db.execute(
                        select(Finding).where(Finding.run_id == run.id)
                    )
                )
                .scalars()
                .all()
            )
            return rows

    rows = asyncio.run(_run())
    assert rows
    assert rows[0].fingerprint == finding_fingerprint(
        "SQL Injection em login", "Aplicação / injeção", "example.com"
    )
