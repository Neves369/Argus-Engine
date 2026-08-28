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


def _sarif_level(severity: str | None, confidence: float) -> str:
    severity = (severity or "").lower()
    if severity in ("critical", "high"):
        return "error"
    if severity == "medium":
        return "warning"
    if severity in ("low", "info"):
        return "note"
    return "error" if confidence >= 0.7 else "note"


def run_findings_sarif(run: Run) -> str:
    """Serialize a run's findings as SARIF 2.1.0 (OASIS SARIF JSON)."""
    findings = (run.result or {}).get("findings") or []
    target = ((run.result or {}).get("target") or {}).get("name") or "unknown"

    rules: list[dict[str, Any]] = []
    rule_index: dict[str, int] = {}
    results: list[dict[str, Any]] = []

    for finding in findings:
        title = str(finding.get("title", "untitled"))
        severity = finding.get("severity")
        confidence = float(finding.get("confidence", 0.0))
        rule_id = f"ARGUS-{severity.upper() if severity else 'UNC'}"

        if rule_id not in rule_index:
            rule_index[rule_id] = len(rules)
            rules.append(
                {
                    "id": rule_id,
                    "name": rule_id,
                    "shortDescription": {
                        "text": f"Argus finding (severity {severity or 'unknown'})"
                    },
                }
            )

        results.append(
            {
                "ruleId": rule_id,
                "ruleIndex": rule_index[rule_id],
                "level": _sarif_level(severity, confidence),
                "message": {"text": title},
                "properties": {
                    "confidence": confidence,
                    "status": finding.get("status", "candidate"),
                    "requires_human_review": finding.get("requires_human_review", False),
                },
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": target},
                        }
                    }
                ],
            }
        )

    doc: dict[str, Any] = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Argus Engine",
                        "informationUri": "https://github.com/",
                        "rules": rules,
                    }
                },
                "results": results,
            }
        ],
    }
    return json.dumps(doc, indent=2, ensure_ascii=False)
