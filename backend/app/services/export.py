from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

import yaml

from app.db.models import Run, Session


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def composition_to_dict(session: Session) -> dict[str, Any]:
    return {
        "id": session.id,
        "name": session.name,
        "status": session.status,
        "target_id": session.target_id,
        "config": session.config,
        "created_at": _iso(session.created_at),
    }


def run_to_dict(run: Run) -> dict[str, Any]:
    return {
        "id": run.id,
        "session_id": run.session_id,
        "target_id": run.target_id,
        "status": run.status,
        "error": run.error,
        "result": run.result,
        "created_at": _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
    }


def run_findings_csv(run: Run) -> str:
    """Flatten run findings into CSV text (title, severity, confidence, description)."""
    findings = (run.result or {}).get("findings") or []
    if not findings:
        return "title,severity,confidence,description\n"

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["title", "severity", "confidence", "description"])
    for finding in findings:
        writer.writerow(
            [
                finding.get("title", ""),
                finding.get("severity", ""),
                finding.get("confidence", ""),
                finding.get("description", ""),
            ]
        )
    return buffer.getvalue()


def serialize(data: dict[str, Any], fmt: str) -> str:
    fmt = (fmt or "json").lower()
    if fmt == "yaml":
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    return json.dumps(data, indent=2, ensure_ascii=False)
