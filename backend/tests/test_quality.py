from __future__ import annotations

from app.db.models import Finding
from app.services.false_positives import FalsePositiveBlacklist
from app.services.quality import QualityScorer, ValidationOutcome, ValidationPipeline


def _finding(**kwargs) -> Finding:
    defaults: dict = {"title": "test", "confidence": 0.8, "severity": None}
    defaults.update(kwargs)
    return Finding(**defaults)


def test_scorer_rewards_evidence_and_confidence():
    scorer = QualityScorer()
    low = scorer.score(_finding(confidence=0.3), 0)
    high = scorer.score(_finding(confidence=0.8), 2)
    assert high > low


def test_pipeline_requires_evidence():
    pipeline = ValidationPipeline(QualityScorer(), FalsePositiveBlacklist([]), threshold=0.6)
    assert pipeline.validate(_finding(confidence=0.9), 0) is ValidationOutcome.NEEDS_REVIEW


def test_pipeline_validates_with_evidence():
    pipeline = ValidationPipeline(QualityScorer(), FalsePositiveBlacklist([]), threshold=0.6)
    assert pipeline.validate(_finding(confidence=0.9), 1) is ValidationOutcome.VALIDATE


def test_pipeline_low_confidence_needs_review():
    pipeline = ValidationPipeline(QualityScorer(), FalsePositiveBlacklist([]), threshold=0.6)
    assert pipeline.validate(_finding(confidence=0.2), 1) is ValidationOutcome.NEEDS_REVIEW


def test_pipeline_high_severity_needs_review():
    pipeline = ValidationPipeline(QualityScorer(), FalsePositiveBlacklist([]), threshold=0.6)
    outcome = pipeline.validate(_finding(confidence=0.9, severity="high"), 1)
    assert outcome is ValidationOutcome.NEEDS_REVIEW


def test_pipeline_blacklist_marks_false_positive():
    blacklist = FalsePositiveBlacklist(["known false positive"])
    pipeline = ValidationPipeline(QualityScorer(), blacklist, threshold=0.6)
    outcome = pipeline.validate(_finding(title="known false positive detected"), 5)
    assert outcome is ValidationOutcome.FALSE_POSITIVE
