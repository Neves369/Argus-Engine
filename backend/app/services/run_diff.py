from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Finding, Run

#: Campos comparados para decidir "changed" vs "unchanged" (severidade,
#: status e confiança arredondada). A identidade é o fingerprint (M9-P0).
_COMPARED_FIELDS = ("severity", "status", "confidence")


def _summary(finding: Finding) -> dict[str, Any]:
    return {
        "id": finding.id,
        "title": finding.title,
        "severity": finding.severity,
        "status": finding.status,
        "confidence": round(float(finding.confidence or 0.0), 3),
        "fingerprint": finding.fingerprint,
    }


async def compare_runs(
    db: AsyncSession, baseline: Run, current: Run
) -> dict[str, Any]:
    """Diff de findings entre dois runs do MESMO alvo, por fingerprint (M9-P1).

    Classifica cada assinatura em ``new`` (só no current), ``resolved`` (só no
    baseline), ``unchanged`` (mesma severidade/status/confiança) e ``changed``
    (assinatura igual, estado mudou). Retorna contagens + listas resumidas.
    """
    if baseline.target_id != current.target_id:
        raise ValueError("runs de alvos distintos não são comparáveis")

    baseline_rows = list(
        (
            await db.execute(
                select(Finding).where(Finding.run_id == baseline.id).order_by(Finding.id)
            )
        )
        .scalars()
        .all()
    )
    current_rows = list(
        (
            await db.execute(
                select(Finding).where(Finding.run_id == current.id).order_by(Finding.id)
            )
        )
        .scalars()
        .all()
    )

    baseline_by_fp: dict[str, Finding] = {}
    for f in baseline_rows:
        if f.fingerprint:
            baseline_by_fp[f.fingerprint] = f
    current_by_fp: dict[str, Finding] = {}
    for f in current_rows:
        if f.fingerprint:
            current_by_fp[f.fingerprint] = f

    new: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    changed: list[dict[str, Any]] = []

    for fp, cur in current_by_fp.items():
        base = baseline_by_fp.get(fp)
        if base is None:
            new.append(_summary(cur))
            continue
        if all(
            getattr(base, field) == getattr(cur, field)
            for field in _COMPARED_FIELDS
        ):
            unchanged.append(_summary(cur))
        else:
            changed.append(
                {
                    "current": _summary(cur),
                    "baseline": _summary(base),
                }
            )

    for fp, base in baseline_by_fp.items():
        if fp not in current_by_fp:
            resolved.append(_summary(base))

    return {
        "baseline_run_id": baseline.id,
        "current_run_id": current.id,
        "target_id": current.target_id,
        "counts": {
            "new": len(new),
            "resolved": len(resolved),
            "unchanged": len(unchanged),
            "changed": len(changed),
        },
        "new": new,
        "resolved": resolved,
        "unchanged": unchanged,
        "changed": changed,
    }
