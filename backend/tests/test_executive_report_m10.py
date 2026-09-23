from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Finding, Run
from app.services.export import (
    EXECUTIVE_TOP_N,
    run_executive_markdown,
    run_executive_report,
)


def _finding(severity: str = "low", title: str = "achado", **overrides) -> Finding:
    defaults = {
        "title": title,
        "severity": severity,
        "category": "Superfície de ataque",
        "affected": "example.com",
        "confidence": 0.7,
        "status": "candidate",
        "requires_human_review": True,
        "meta": {"evidence": "GET /x -> 200", "probe_url": "http://example.com/x"},
        "description": "descrição",
        "remediation": "corrigir",
    }
    defaults.update(overrides)
    return Finding(**defaults)


def _run(authorization_note: str | None = None) -> Run:
    target: dict = {"name": "example.com"}
    if authorization_note:
        target["authorization_note"] = authorization_note
    return Run(
        id=7,
        status="completed",
        result={
            "target": target,
            "tokens_used": 1200,
            "cost": 0.04,
            "confidence": 0.8,
            "stop_reason": "confidence",
            "scan": [
                {
                    "target": "example.com",
                    "depth": "deep",
                    "auth_status": "success",
                    "auth_cookies": ["PHPSESSID"],
                }
            ],
        },
        created_at=datetime.now(UTC),
        finished_at=datetime.now(UTC),
    )


def test_executive_report_structure():
    report = run_executive_report(_run(), [_finding("high", "Servidor divulga versão")])
    assert report["view"] == "executive"
    assert report["run_id"] == 7
    assert report["target"] == "example.com"
    assert report["summary"]["total_findings"] == 1
    assert report["top_findings"][0]["title"] == "Servidor divulga versão"
    assert report["top_findings"][0]["remediation"] == "corrigir"


def test_executive_report_strips_technical_evidence():
    report = run_executive_report(_run(), [_finding("medium", "reflexão observada")])
    top = report["top_findings"][0]
    assert "evidence" not in top
    assert "probe_url" not in top
    assert "description" not in top


def test_executive_report_orders_by_severity():
    findings = [
        _finding("info", "info"),
        _finding("critical", "crítico"),
        _finding("low", "baixo"),
    ]
    report = run_executive_report(_run(), findings)
    assert [f["severity"] for f in report["top_findings"]] == [
        "critical",
        "low",
        "info",
    ]


def test_executive_report_caps_top_findings():
    findings = [_finding("low", f"achado-{i}") for i in range(EXECUTIVE_TOP_N + 5)]
    report = run_executive_report(_run(), findings)
    assert len(report["top_findings"]) == EXECUTIVE_TOP_N


def test_executive_report_includes_authorization():
    note = "Autorizado pelo time X"
    report = run_executive_report(_run(note), [])
    assert report["authorization"] == note


def test_executive_markdown_has_no_evidence():
    md = run_executive_markdown(_run(), [_finding("high", "Servidor divulga versão")])
    assert "# Relatório executivo" in md
    assert "Servidor divulga versão" in md
    assert "Evidência" not in md


def test_report_view_invalid_is_bad_request(client):
    resp = client.get("/api/v1/runs/99999/report", params={"view": "bogus"})
    assert resp.status_code == 400


def test_export_view_invalid_is_bad_request(client):
    resp = client.get("/api/v1/runs/99999/export", params={"format": "json", "view": "bogus"})
    assert resp.status_code == 400
