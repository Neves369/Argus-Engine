from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

import yaml

from app.db.models import Finding, Run, Session

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _duration_ms(started: datetime | None, finished: datetime | None) -> int | None:
    if started is None or finished is None:
        return None
    delta = (finished - started).total_seconds() * 1000
    return int(delta) if delta >= 0 else None


def _severity_rank(finding: Finding) -> int:
    return SEVERITY_ORDER.get((finding.severity or "").lower(), 99)


def _ordered(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=_severity_rank)


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


def finding_report(finding: Finding) -> dict[str, Any]:
    """A single finding rendered for a security report (relatar, não ensinar)."""
    meta = finding.meta or {}
    return {
        "id": finding.id,
        "title": finding.title,
        "severity": finding.severity,
        "category": finding.category,
        "affected": finding.affected,
        "cvss_score": finding.cvss_score,
        "cvss_vector": finding.cvss_vector,
        "cves": finding.cves or [],
        "known_exploits": finding.known_exploits or [],
        "description": finding.description,
        "evidence": meta.get("evidence"),
        "remediation": finding.remediation,
        "references": finding.references or [],
        "confidence": finding.confidence,
        "status": finding.status,
        "requires_human_review": finding.requires_human_review,
    }


def run_report(run: Run, findings: list[Finding]) -> dict[str, Any]:
    """Structured security report: what was found, severity, exploits, remediation.

    Observability (tokens/cost) is kept, but in its own appendix rather than as
    the headline content.
    """
    result = run.result or {}
    target = (result.get("target") or {}).get("name") or "unknown"

    by_severity: dict[str, int] = {}
    for finding in findings:
        key = (finding.severity or "unknown").lower()
        by_severity[key] = by_severity.get(key, 0) + 1

    return {
        "run_id": run.id,
        "target": target,
        "status": run.status,
        "generated_at": _iso(run.finished_at) or _iso(run.created_at),
        "started_at": _iso(run.started_at),
        "finished_at": _iso(run.finished_at),
        "duration_ms": _duration_ms(run.started_at, run.finished_at),
        "trace": (result.get("trace") or []),
        "history": (result.get("history") or []),
        "pending_review": (result.get("pending_review") or None),
        "summary": {
            "total_findings": len(findings),
            "by_severity": by_severity,
            "pending_review": sum(1 for f in findings if f.requires_human_review),
        },
        "findings": [finding_report(f) for f in _ordered(findings)],
        "observability": {
            "tokens_used": result.get("tokens_used", 0),
            "cost": result.get("cost", 0.0),
            "confidence": result.get("confidence"),
            "stop_reason": result.get("stop_reason"),
        },
    }


def run_report_markdown(run: Run, findings: list[Finding]) -> str:
    result = run.result or {}
    target = (result.get("target") or {}).get("name") or "unknown"
    lines: list[str] = [
        "# Relatório de segurança",
        "",
        f"- **Alvo:** {target}",
        f"- **Run:** #{run.id}",
        f"- **Status:** {run.status}",
        f"- **Achados:** {len(findings)}",
        "",
        "## Achados",
        "",
    ]

    if not findings:
        lines.append("Nenhum achado registrado neste run.")
        lines.append("")

    for finding in _ordered(findings):
        severity = finding.severity or "n/a"
        lines.append(f"## [{severity.upper()}] {finding.title}")
        lines.append("")
        lines.append(f"- **Gravidade:** {severity}")
        if finding.category:
            lines.append(f"- **Categoria:** {finding.category}")
        if finding.affected:
            lines.append(f"- **Afetado:** {finding.affected}")
        if finding.cvss_score is not None:
            vector = f" ({finding.cvss_vector})" if finding.cvss_vector else ""
            lines.append(f"- **CVSS:** {finding.cvss_score}{vector}")
        if finding.cves:
            lines.append(f"- **CVEs:** {', '.join(finding.cves)}")
        if finding.known_exploits:
            lines.append(f"- **Exploits conhecidos:** {'; '.join(finding.known_exploits)}")
        lines.append(f"- **Status:** {finding.status}")
        if finding.description:
            lines.append("")
            lines.append(finding.description)
        evidence = (finding.meta or {}).get("evidence")
        if evidence:
            lines.append("")
            lines.append(f"**Evidência:** {evidence}")
        if finding.remediation:
            lines.append("")
            lines.append(f"**Remediação:** {finding.remediation}")
        if finding.references:
            lines.append("")
            lines.append("**Referências:**")
            for ref in finding.references:
                lines.append(f"- {ref}")
        lines.append("")

    lines.extend(
        [
            "## Observabilidade",
            "",
            f"- Tokens: {result.get('tokens_used', 0)}",
            f"- Custo: ${result.get('cost', 0.0):.4f}",
            f"- Confiança do grafo: {result.get('confidence')}",
            f"- Motivo de parada: {result.get('stop_reason')}",
            "",
        ]
    )
    return "\n".join(lines)


def run_findings_csv(findings: list[Finding]) -> str:
    """Flatten findings into CSV text for spreadsheet consumption."""
    header = [
        "title",
        "severity",
        "category",
        "affected",
        "cvss_score",
        "cves",
        "known_exploits",
        "remediation",
        "confidence",
        "status",
    ]
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(header)
    for finding in _ordered(findings):
        writer.writerow(
            [
                finding.title,
                finding.severity or "",
                finding.category or "",
                finding.affected or "",
                finding.cvss_score if finding.cvss_score is not None else "",
                "; ".join(finding.cves or []),
                "; ".join(finding.known_exploits or []),
                finding.remediation or "",
                finding.confidence,
                finding.status,
            ]
        )
    return buffer.getvalue()


def serialize(data: dict[str, Any], fmt: str) -> str:
    fmt = (fmt or "json").lower()
    if fmt == "yaml":
        return yaml.safe_dump(data, sort_keys=False, allow_unicode=True)
    return json.dumps(data, indent=2, ensure_ascii=False)


def _sarif_level(severity: str | None) -> str:
    severity = (severity or "").lower()
    if severity in ("critical", "high"):
        return "error"
    if severity == "medium":
        return "warning"
    if severity in ("low", "info"):
        return "note"
    return "note"


def run_findings_sarif(run: Run, findings: list[Finding]) -> str:
    """Serialize a run's findings as SARIF 2.1.0 (OASIS SARIF JSON)."""
    result = run.result or {}
    target = (result.get("target") or {}).get("name") or "unknown"

    rules: list[dict[str, Any]] = []
    rule_index: dict[str, int] = {}
    results: list[dict[str, Any]] = []

    for finding in _ordered(findings):
        severity = finding.severity or "unknown"
        rule_id = f"ARGUS-{severity.upper()}"

        if rule_id not in rule_index:
            rule_index[rule_id] = len(rules)
            rules.append(
                {
                    "id": rule_id,
                    "name": rule_id,
                    "shortDescription": {
                        "text": f"Argus finding (severity {severity})"
                    },
                }
            )

        properties: dict[str, Any] = {
            "confidence": finding.confidence,
            "status": finding.status,
            "requires_human_review": finding.requires_human_review,
        }
        if finding.cvss_score is not None:
            properties["cvss_score"] = finding.cvss_score
            properties["cvss_vector"] = finding.cvss_vector
        if finding.cves:
            properties["cves"] = finding.cves
        if finding.known_exploits:
            properties["known_exploits"] = finding.known_exploits
        if finding.remediation:
            properties["remediation"] = finding.remediation

        results.append(
            {
                "ruleId": rule_id,
                "ruleIndex": rule_index[rule_id],
                "level": _sarif_level(severity),
                "message": {"text": finding.title},
                "properties": properties,
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
