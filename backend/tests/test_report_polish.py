from __future__ import annotations

from datetime import UTC, datetime

from app.db.models import Finding, Run
from app.services.export import (
    finding_report,
    run_report,
    run_report_markdown,
    run_report_pdf,
)


def _finding(**overrides) -> Finding:
    defaults = {
        "title": "achado genérico",
        "severity": "low",
        "category": "Superfície de ataque",
        "affected": "example.com",
        "confidence": 0.7,
        "status": "candidate",
        "requires_human_review": True,
        "meta": {},
        "description": "descrição",
        "remediation": "corrigir",
    }
    defaults.update(overrides)
    return Finding(**defaults)


def _run(**overrides) -> Run:
    defaults = {
        "id": 7,
        "status": "completed",
        "result": {
            "target": {"name": "example.com"},
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
                    "auth": "login dinâmico aplicado",
                    "pages": [],
                }
            ],
        },
        "created_at": datetime.now(UTC),
    }
    defaults.update(overrides)
    return Run(**defaults)


def _polished_findings() -> list[Finding]:
    return [
        _finding(
            title="Headers de segurança ausentes na resposta",
            severity="medium",
            category="A05:2021 Security Misconfiguration",
        ),
        _finding(
            title="Serviço exposto em porta TCP comum",
            category="Superfície de ataque",
        ),
        _finding(
            title="3 formulário(s) com entrada de dados observados no crawl",
            category="Aplicação / vetores de entrada",
            meta={
                "extras": {
                    "form_count": 3,
                    "route_count": 2,
                    "routes": [
                        {
                            "url": "http://example.com/login.php",
                            "method": "POST",
                            "fields": ["user", "pass"],
                            "sensitive_fields": ["pass"],
                        }
                    ],
                }
            },
        ),
        _finding(
            title="2 parâmetro(s) refletido(s) no corpo da resposta",
            category="Aplicação / reflexão observada",
            meta={"extras": {"reflection_count": 2}},
        ),
        _finding(
            title="Erro verboso exposto em /login.php",
            severity="low",
            category="Aplicação / informação sensível em erro",
            meta={"markers_hint": True},
        ),
        _finding(
            title="4 rota(s) de aplicação descobertas + 1 estático(s)",
            category="Aplicação / superfície de rotas",
            meta={"extras": {"app_route_count": 4, "static_count": 1}},
        ),
    ]


def test_report_json_has_executive_summary():
    run = _run()
    findings = _polished_findings()
    report = run_report(run, findings)

    summary = report["summary"]["executive"]
    assert summary["superficie"] == 1
    assert summary["configuracao"] == 1
    assert summary["aplicacao"] == 4
    assert summary["aplicacao_breakdown"] == {
        "forms": 3,
        "reflections": 2,
        "verbose_errors": 1,
        "routes": 4,
        "api_endpoints": 0,
    }
    assert summary["validated"] == 0
    assert summary["candidate"] == 6
    assert summary["depth"] == "deep"
    assert summary["auth"] == "success"
    assert summary["auth_cookie_names"] == ["PHPSESSID"]


def test_report_json_never_leaks_cookie_values():
    run = _run()
    report = run_report(run, _polished_findings())
    rendered = str(report)
    assert "PHPSESSID" in rendered  # nome do cookie é aceitável
    assert "login dinâmico aplicado" in rendered


def test_markdown_has_resume_block_before_achados():
    run = _run()
    md = run_report_markdown(run, _polished_findings())

    assert md.index("## Resumo") < md.index("## Achados")
    assert "**Profundidade:** deep" in md
    assert "**Auth:** success (cookies: PHPSESSID)" in md
    assert "**Validados:** 0 | **Candidatos:** 6" in md
    assert "formulários: 3" in md


def test_markdown_shows_reprobe_evidence():
    run = _run()
    findings = _polished_findings()
    forms = next(
        f for f in findings if f.title.startswith("3 formulário(s)")
    )
    forms.meta = {**(forms.meta or {}), "reprobe": _reprobe()}
    md = run_report_markdown(run, [forms])

    assert "**Re-probe:** ok" in md
    assert "http_request -> http://example.com/login.php" in md


def test_finding_report_exposes_reprobe_and_extras():
    finding = _finding(
        category="Aplicação / superfície de rotas",
        meta={
            "image": None,
            "evidence": "GET / -> 200",
            "extras": {"app_route_count": 4},
            "reprobe": _reprobe(),
        },
    )
    report = finding_report(finding)
    assert report["reprobe"]["ok"] is True
    assert report["extras"]["app_route_count"] == 4


def test_report_pdf_builds_with_resume():
    run = _run()
    run.finished_at = datetime.now(UTC)
    run.started_at = datetime.now(UTC)
    pdf = run_report_pdf(run, _polished_findings())
    assert pdf.startswith(b"%PDF")


def _reprobe() -> dict:
    return {
        "tool": "http_request",
        "url": "http://example.com/login.php",
        "ok": True,
        "status_code": 200,
        "last_probed_at": "2026-01-01T00:00:00+00:00",
    }