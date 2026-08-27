from __future__ import annotations

import enum

from app.db.models import Finding
from app.services.false_positives import FalsePositiveBlacklist


class ValidationOutcome(enum.StrEnum):
    VALIDATE = "validate"
    FALSE_POSITIVE = "false_positive"
    NEEDS_REVIEW = "needs_review"


HIGH_SEVERITY = {"critical", "high"}

_SEVERITY_WEIGHT = {
    "critical": 0.15,
    "high": 0.12,
    "medium": 0.08,
    "low": 0.0,
}


class QualityScorer:
    @staticmethod
    def score(finding: Finding, evidence_count: int) -> float:
        confidence = max(0.0, min(1.0, finding.confidence))
        evidence = min(evidence_count, 2) * 0.15
        severity = _SEVERITY_WEIGHT.get(finding.severity or "", 0.05)
        return round(min(1.0, confidence * 0.7 + evidence + severity), 3)


class ValidationPipeline:
    """Decides whether a finding can be promoted to validated.

    Only findings with evidence and a sufficient quality score are validated.
    High-severity findings and those matching the blacklist are handled specially.
    """

    def __init__(
        self,
        scorer: QualityScorer,
        blacklist: FalsePositiveBlacklist,
        *,
        threshold: float = 0.6,
    ) -> None:
        self.scorer = scorer
        self.blacklist = blacklist
        self.threshold = threshold

    def validate(self, finding: Finding, evidence_count: int) -> ValidationOutcome:
        if self.blacklist.matches(finding):
            return ValidationOutcome.FALSE_POSITIVE
        if finding.severity in HIGH_SEVERITY:
            return ValidationOutcome.NEEDS_REVIEW
        if evidence_count < 1:
            return ValidationOutcome.NEEDS_REVIEW
        if self.scorer.score(finding, evidence_count) >= self.threshold:
            return ValidationOutcome.VALIDATE
        return ValidationOutcome.NEEDS_REVIEW
