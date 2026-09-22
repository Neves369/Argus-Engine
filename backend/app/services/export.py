from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any
from xml.sax.saxutils import escape

import yaml

from app.db.models import Finding, Run, Session

SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
    "info": 4,
}

# Seções do relatório (Etapa M4): o operador identifica de imediato o que é
# superfície/configuração vs aplicação vs correlação de CVE.
SECTION_SUPERFICIE = "superficie"
SECTION_CONFIG = "configuracao"
SECTION_APP = "aplicacao"
SECTION_BEHAVIOR = "comportamento"
SECTION_CORRELACAO = "correlacao"

SECTION_LABELS = {
    SECTION_SUPERFICIE: "Superfície",
    SECTION_CONFIG: "Configuração",
    SECTION_APP: "Aplicação",
    SECTION_BEHAVIOR: "Comportamento",
    SECTION_CORRELACAO: "Correlação CVE",
}

_SECTION_ORDER = (
    SECTION_SUPERFICIE,
    SECTION_CONFIG,
    SECTION_APP,
    SECTION_BEHAVIOR,
    SECTION_CORRELACAO,
)


def finding_section(finding: Finding) -> str:
    """Classifica um finding em uma das seções do relatório.

    Determinístico, baseado na ``category`` (OWASP/categorias já usadas pelos
    extractors): A06 → correlação CVE; A03/CWE-601 → aplicação; A05/A02 →
    configuração; prefixo "Comportamento" (Etapa M6) → seção Comportamento; o
    restante (superfície de ataque, reputação de rede, gestão de domínio,
    leads) → superfície.
    """
    category = (finding.category or "").strip().lower()
    if category.startswith("comportamento"):
        return SECTION_BEHAVIOR
    if "a06" in category or "outdated components" in category:
        return SECTION_CORRELACAO
    if "a03" in category or "injection" in category or "cwe-601" in category:
        return SECTION_APP
    if "aplicação" in category:
        return SECTION_APP
    if (
        "a05" in category
        or "a02" in category
        or "misconfiguration" in category
        or "cryptographic" in category
    ):
        return SECTION_CONFIG
    return SECTION_SUPERFICIE


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
        "section": finding_section(finding),
        "affected": finding.affected,
        "cvss_score": finding.cvss_score,
        "cvss_vector": finding.cvss_vector,
        "cves": finding.cves or [],
        "known_exploits": finding.known_exploits or [],
        "description": finding.description,
        "evidence": meta.get("evidence"),
        "probe_url": meta.get("probe_url"),
        "remediation": finding.remediation,
        "references": finding.references or [],
        "confidence": finding.confidence,
        "status": finding.status,
        "requires_human_review": finding.requires_human_review,
        "verification": meta.get("verification"),
        "reprobe": meta.get("reprobe"),
        "extras": (meta.get("extras") or {}),
    }


def _section_for(category: str | None) -> str:
    """Map a finding category to one of the report's stable sections.

    ``Aplicação``-prefixed categories (M1 polish) land in "Aplicação"; OWASP
    Top-10 categories (e.g. A02/A05 misconfig) land in "Configuração";
    "Comportamento" (Etapa M6) lands in "Comportamento"; everything else falls
    back to "Superfície".
    """
    cat = (category or "").strip()
    if cat.startswith("Comportamento"):
        return "comportamento"
    if cat.startswith("Aplicação"):
        return "aplicacao"
    if cat.startswith("A"):
        return "configuracao"
    return "superficie"


def _executive_summary(run: Run, findings: list[Finding]) -> dict[str, Any]:
    """One-glance summary: surface/config/application/behavior + auth/depth.

    ``aplicacao_breakdown`` counts come from the aggregated ``extras``
    (routes/reflections) so the headline mirrors what the crawl actually
    observed. ``depth`` and ``auth`` are read from the scan part of the graph
    result (auth cookies are listed by name only, never by value).
    """
    sections: dict[str, list[Finding]] = {
        "superficie": [],
        "configuracao": [],
        "aplicacao": [],
        "comportamento": [],
    }
    for finding in findings:
        sections[_section_for(finding.category)].append(finding)

    applied = sections["aplicacao"]
    forms = 0
    reflections = 0
    errors = 0
    routes = 0
    for finding in applied:
        extras = (finding.meta or {}).get("extras") or {}
        category = (finding.category or "")
        if category == "Aplicação / informação sensível em erro":
            errors += 1
        if category == "Aplicação / superfície de rotas":
            routes += int(extras.get("app_route_count") or 1)
        forms += int(extras.get("form_count") or 0)
        reflections += int(extras.get("reflection_count") or 0)

    validated = sum(1 for f in findings if (f.status or "") == "validated")
    scan = (run.result or {}).get("scan") or []
    first_scan = scan[0] if scan else {}
    summary: dict[str, Any] = {
        "superficie": len(sections["superficie"]),
        "configuracao": len(sections["configuracao"]),
        "aplicacao": len(sections["aplicacao"]),
        "comportamento": len(sections["comportamento"]),
        "aplicacao_breakdown": {
            "forms": forms,
            "reflections": reflections,
            "verbose_errors": errors,
            "routes": routes,
        },
        "validated": validated,
        "candidate": len(findings) - validated,
        "depth": first_scan.get("depth") or "quick",
        "auth": first_scan.get("auth_status") or "skipped",
    }
    if first_scan.get("sessions"):
        summary["sessions"] = [
            {
                "name": s.get("name"),
                "auth_status": s.get("auth_status"),
                "page_count": s.get("page_count") or 0,
            }
            for s in first_scan["sessions"]
        ]
    if first_scan.get("auth_cookies"):
        summary["auth_cookie_names"] = list(first_scan["auth_cookies"])
    if first_scan.get("auth"):
        summary["auth_note"] = first_scan["auth"]
    return summary


def _section_summary(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {section: 0 for section in _SECTION_ORDER}
    for finding in findings:
        section = finding_section(finding)
        counts[section] = counts.get(section, 0) + 1
    return counts


def run_report(run: Run, findings: list[Finding]) -> dict[str, Any]:
    """Structured security report: what was found, severity, exploits, remediation.

    Observability (tokens/cost) is kept, but in its own appendix rather than as
    the headline content. Findings are also bucketed into the four report
    sections (Etapa M4) so config vs app vs CVE-correlation is immediately
    distinguishable.
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
        "resumable": run.status in ("cancelled", "failed") and bool(run.result),
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
            "by_section": _section_summary(findings),
            "pending_review": sum(1 for f in findings if f.requires_human_review),
            "executive": _executive_summary(run, findings),
        },
        "findings": [finding_report(f) for f in _ordered(findings)],
        "observability": {
            "tokens_used": result.get("tokens_used", 0),
            "cost": result.get("cost", 0.0),
            "confidence": result.get("confidence"),
            "stop_reason": result.get("stop_reason"),
        },
    }


def _finding_markdown_lines(finding: Finding) -> list[str]:
    """Render one finding as Markdown (relatar, não ensinar)."""
    lines: list[str] = []
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
    reprobe = (finding.meta or {}).get("reprobe")
    if reprobe:
        state = "ok" if reprobe.get("ok") else "falha"
        lines.append("")
        lines.append(
            f"**Re-probe:** {state} "
            f"({reprobe.get('tool')} -> {reprobe.get('url')}, "
            f"HTTP {reprobe.get('status_code')}, "
            f"{reprobe.get('last_probed_at')})"
        )
    if finding.remediation:
        lines.append("")
        lines.append(f"**Remediação:** {finding.remediation}")
    if finding.references:
        lines.append("")
        lines.append("**Referências:**")
        for ref in finding.references:
            lines.append(f"- {ref}")
    lines.append("")
    return lines


def run_report_markdown(run: Run, findings: list[Finding]) -> str:
    result = run.result or {}
    target = (result.get("target") or {}).get("name") or "unknown"
    execu = _executive_summary(run, findings)
    auth_line = f"- **Auth:** {execu['auth']}"
    if execu.get("auth_cookie_names"):
        auth_line += f" (cookies: {', '.join(execu['auth_cookie_names'])})"
    lines: list[str] = [
        "# Relatório de segurança",
        "",
        f"- **Alvo:** {target}",
        f"- **Run:** #{run.id}",
        f"- **Status:** {run.status}",
        f"- **Achados:** {len(findings)}",
        "",
        "## Resumo",
        "",
        f"- **Superfície:** {execu['superficie']}",
        f"- **Configuração:** {execu['configuracao']}",
        (
            f"- **Aplicação:** {execu['aplicacao']} "
            f"(formulários: {execu['aplicacao_breakdown']['forms']}, "
            f"reflexões: {execu['aplicacao_breakdown']['reflections']}, "
            f"erros verbosos: {execu['aplicacao_breakdown']['verbose_errors']}, "
            f"rotas: {execu['aplicacao_breakdown']['routes']})"
        ),
        f"- **Validados:** {execu['validated']} | **Candidatos:** {execu['candidate']}",
        f"- **Profundidade:** {execu['depth']}",
        auth_line,
        "",
        "## Achados",
        "",
    ]

    if not findings:
        lines.append("Nenhum achado registrado neste run.")
        lines.append("")

    # Achados organizados por seção (Etapa M4): Superfície | Configuração |
    # Aplicação | Correlação CVE — o operador distingue config de app na hora.
    by_section: dict[str, list[Finding]] = {section: [] for section in _SECTION_ORDER}
    for finding in _ordered(findings):
        by_section[finding_section(finding)].append(finding)

    for section in _SECTION_ORDER:
        bucket = by_section[section]
        if not bucket:
            continue
        lines.append(f"## {SECTION_LABELS[section]}")
        lines.append("")
        for finding in bucket:
            lines.extend(_finding_markdown_lines(finding))

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


def _pdf_escape(value: str | None) -> str:
    """Escape text for the Platypus MiniML parser.

    Finding descriptions come from scanning (headers, pages) and external
    feeds (NVD) and may legitimately contain ``<``/``&`` that Paragraph would
    otherwise interpret as markup.
    """
    return escape(value or "")


def run_report_pdf(run: Run, findings: list[Finding]) -> bytes:
    """Render the security report as a printable PDF (relatar, não ensinar).

    Content mirrors ``run_report_markdown``: summary, per-finding detail
    (severity, CVSS, CVEs, exploits, remediation) and an observability
    appendix — the same report policy as the other formats.
    """
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    result = run.result or {}
    target = (result.get("target") or {}).get("name") or "unknown"
    execu = _executive_summary(run, findings)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
    )

    styles = getSampleStyleSheet()
    h1 = styles["Title"]
    h2 = styles["Heading2"]
    body = styles["BodyText"]
    small = ParagraphStyle("small", parent=body, fontSize=9, textColor=colors.grey)

    def _label_pairs(items: list[tuple[str, str | None]]) -> Paragraph:
        text = "<br/>".join(
            f"<b>{_pdf_escape(k)}:</b> {_pdf_escape(v)}" for k, v in items
        )
        return Paragraph(text, body)

    story: list[Any] = [
        Paragraph("Relatório de segurança", h1),
        Spacer(1, 3 * mm),
        _label_pairs(
            [
                ("Alvo", target),
                ("Run", f"#{run.id}"),
                ("Status", run.status),
                ("Achados", str(len(findings))),
            ]
        ),
        Spacer(1, 4 * mm),
        Paragraph("Resumo", h2),
        _label_pairs(
            [
                ("Superfície", str(execu["superficie"])),
                ("Configuração", str(execu["configuracao"])),
                (
                    "Aplicação",
                    f"{execu['aplicacao']} "
                    f"(formulários: {execu['aplicacao_breakdown']['forms']}, "
                    f"reflexões: {execu['aplicacao_breakdown']['reflections']}, "
                    f"erros verbosos: {execu['aplicacao_breakdown']['verbose_errors']}, "
                    f"rotas: {execu['aplicacao_breakdown']['routes']})",
                ),
                ("Validados / Candidatos", f"{execu['validated']} / {execu['candidate']}"),
                ("Profundidade", execu["depth"]),
                (
                    "Auth",
                    execu["auth"]
                    + (
                        f" (cookies: {', '.join(execu['auth_cookie_names'])})"
                        if execu.get("auth_cookie_names")
                        else ""
                    ),
                ),
            ]
        ),
        Spacer(1, 4 * mm),
    ]

    by_severity: dict[str, int] = {}
    for finding in findings:
        key = (finding.severity or "unknown").lower()
        by_severity[key] = by_severity.get(key, 0) + 1

    if by_severity:
        story.append(Paragraph("Resumo por gravidade", h2))
        rows = [["Gravidade", "Qtd."]]
        rows.extend([[s, str(c)] for s, c in sorted(by_severity.items())])
        table = Table(rows, colWidths=[60 * mm, 30 * mm])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.92, 0.92, 0.92)),
                ]
            )
        )
        story.append(table)
        story.append(Spacer(1, 4 * mm))

    if not findings:
        story.append(Paragraph("Nenhum achado registrado neste run.", body))
    else:
        for finding in _ordered(findings):
            title = f"[{finding.severity or 'N/A'}] {_pdf_escape(finding.title)}"
            story.append(Paragraph(title, h2))
            pairs: list[tuple[str, str | None]] = [
                ("Gravidade", finding.severity),
            ]
            if finding.category:
                pairs.append(("Categoria", finding.category))
            if finding.affected:
                pairs.append(("Afetado", finding.affected))
            if finding.cvss_score is not None:
                vector = f" ({finding.cvss_vector})" if finding.cvss_vector else ""
                pairs.append(("CVSS", f"{finding.cvss_score}{vector}"))
            if finding.cves:
                pairs.append(("CVEs", ", ".join(finding.cves)))
            if finding.known_exploits:
                pairs.append(("Exploits conhecidos", "; ".join(finding.known_exploits)))
            pairs.append(("Status", finding.status))
            story.append(_label_pairs(pairs))
            if finding.description:
                story.append(Spacer(1, 1 * mm))
                story.append(Paragraph(_pdf_escape(finding.description), body))
            evidence = (finding.meta or {}).get("evidence")
            if evidence:
                story.append(Spacer(1, 1 * mm))
                story.append(Paragraph(f"<b>Evidência:</b> {_pdf_escape(str(evidence))}", body))
            reprobe = (finding.meta or {}).get("reprobe")
            if reprobe:
                state = "ok" if reprobe.get("ok") else "falha"
                story.append(Spacer(1, 1 * mm))
                story.append(
                    Paragraph(
                        f"<b>Re-probe:</b> {state} "
                        f"({_pdf_escape(reprobe.get('tool') or '')} -> "
                        f"{_pdf_escape(reprobe.get('url') or '')}, "
                        f"HTTP {_pdf_escape(reprobe.get('status_code') or '')}, "
                        f"{_pdf_escape(reprobe.get('last_probed_at') or '')})",
                        body,
                    )
                )
            if finding.remediation:
                story.append(Spacer(1, 1 * mm))
                remediation = f"<b>Remediação:</b> {_pdf_escape(finding.remediation)}"
                story.append(Paragraph(remediation, body))
            if finding.references:
                story.append(Spacer(1, 1 * mm))
                story.append(Paragraph("<b>Referências:</b>", body))
                for ref in finding.references:
                    story.append(Paragraph(f"- {_pdf_escape(ref)}", small))
            story.append(Spacer(1, 3 * mm))

    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Observabilidade", h2))
    story.append(
        Paragraph(
            f"Tokens: {result.get('tokens_used', 0)}<br/>"
            f"Custo: ${float(result.get('cost', 0.0)):.4f}<br/>"
            f"Confiança do grafo: {_pdf_escape(str(result.get('confidence')))}<br/>"
            f"Motivo de parada: {_pdf_escape(str(result.get('stop_reason')))}",
            body,
        )
    )
    def _footer(canvas, _docx: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"Argus Engine — {target}")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
