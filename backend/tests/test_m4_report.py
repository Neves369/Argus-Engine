from __future__ import annotations

from app.db.models import Finding, Run
from app.services.export import (
    SECTION_APP,
    SECTION_CONFIG,
    SECTION_CORRELACAO,
    SECTION_SUPERFICIE,
    finding_section,
    run_report,
    run_report_markdown,
)
from app.services.false_positives import FalsePositiveBlacklist
from app.services.quality import QualityScorer, ValidationOutcome, ValidationPipeline


def _finding(**kwargs) -> Finding:
    defaults: dict = {"title": "t", "confidence": 0.8, "severity": "low"}
    defaults.update(kwargs)
    return Finding(**defaults)


def _run(**kwargs) -> Run:
    defaults: dict = {
        "id": 1,
        "status": "completed",
        "result": {"target": {"name": "example.com"}, "tokens_used": 0, "cost": 0.0},
    }
    defaults.update(kwargs)
    return Run(**defaults)


# ---------------------------------------------------------------------------
# Seções do relatório (Etapa M4)
# ---------------------------------------------------------------------------


def test_finding_section_config():
    assert (
        finding_section(_finding(category="A05:2021 Security Misconfiguration"))
        == SECTION_CONFIG
    )
    assert (
        finding_section(_finding(category="A02:2021 Cryptographic Failures"))
        == SECTION_CONFIG
    )


def test_finding_section_app():
    assert (
        finding_section(_finding(category="A03:2021 Injection (leads passivos)"))
        == SECTION_APP
    )
    assert (
        finding_section(_finding(category="CWE-601: URL Redirection to Untrusted Site"))
        == SECTION_APP
    )
    assert (
        finding_section(_finding(category="Aplicação (módulos/rotas observados)"))
        == SECTION_APP
    )


def test_finding_section_correlacao():
    assert (
        finding_section(_finding(category="A06:2021 Vulnerable and Outdated Components"))
        == SECTION_CORRELACAO
    )


def test_finding_section_superficie_default():
    assert finding_section(_finding(category="Superfície de ataque")) == SECTION_SUPERFICIE
    assert finding_section(_finding(category="Reputação de rede")) == SECTION_SUPERFICIE


def test_run_report_summary_by_section():
    findings = [
        _finding(category="Superfície de ataque"),
        _finding(category="A05:2021 Security Misconfiguration"),
        _finding(category="A03:2021 Injection (leads passivos)"),
        _finding(category="A06:2021 Vulnerable and Outdated Components"),
    ]
    report = run_report(_run(), findings)

    assert report["summary"]["by_section"] == {
        "superficie": 1,
        "configuracao": 1,
        "aplicacao": 1,
        "comportamento": 0,
        "correlacao": 1,
    }
    sections = {f["section"] for f in report["findings"]}
    assert sections == {"superficie", "configuracao", "aplicacao", "correlacao"}


def test_run_report_markdown_groups_by_section():
    findings = [
        _finding(
            title="Header ausente", category="A05:2021 Security Misconfiguration", severity="low"
        ),
        _finding(
            title="Form com entrada",
            category="A03:2021 Injection (leads passivos)",
            severity="info",
        ),
        _finding(title="Subdomínio", category="Superfície de ataque", severity="info"),
    ]
    markdown = run_report_markdown(_run(), findings)

    assert "## Superfície" in markdown
    assert "## Configuração" in markdown
    assert "## Aplicação" in markdown
    # A ordem das seções é fixa e a do conteúdo é determinística.
    assert markdown.index("## Superfície") < markdown.index("## Configuração")
    assert markdown.index("## Configuração") < markdown.index("## Aplicação")


# ---------------------------------------------------------------------------
# Validação conservadora (Etapa M4)
# ---------------------------------------------------------------------------


def _pipeline() -> ValidationPipeline:
    return ValidationPipeline(QualityScorer(), FalsePositiveBlacklist([]), threshold=0.6)


def test_medium_severity_requires_review():
    finding = _finding(severity="medium", confidence=0.9, meta={})
    assert _pipeline().validate(finding, 1) is ValidationOutcome.NEEDS_REVIEW


def test_refuted_live_verification_never_validates():
    finding = _finding(
        severity="low", confidence=0.95, meta={"verification": {"confirmed": False}}
    )
    assert _pipeline().validate(finding, 1) is ValidationOutcome.NEEDS_REVIEW


def test_confirmed_live_verification_counts_as_evidence():
    finding = _finding(
        severity="low", confidence=0.95, meta={"verification": {"confirmed": True}}
    )
    assert _pipeline().validate(finding, 0) is ValidationOutcome.VALIDATE


def test_low_severity_still_validates_with_evidence():
    finding = _finding(severity="low", confidence=0.9, meta={})
    assert _pipeline().validate(finding, 1) is ValidationOutcome.VALIDATE
