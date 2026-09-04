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
        judge=None,
    ) -> None:
        self.scorer = scorer
        self.blacklist = blacklist
        self.threshold = threshold
        self.judge = judge

    def _rules(self, finding: Finding, evidence_count: int) -> tuple[ValidationOutcome, bool]:
        """Apply hard rules; return (outcome, is_hard_stop).

        Hard stops (blacklist, high severity, missing evidence) must never be
        overridden by the LLM judge, preserving security/HITL guarantees.
        """
        if self.blacklist.matches(finding):
            return ValidationOutcome.FALSE_POSITIVE, True
        if finding.severity in HIGH_SEVERITY:
            return ValidationOutcome.NEEDS_REVIEW, True
        if evidence_count < 1:
            return ValidationOutcome.NEEDS_REVIEW, True
        if self.scorer.score(finding, evidence_count) >= self.threshold:
            return ValidationOutcome.VALIDATE, False
        return ValidationOutcome.NEEDS_REVIEW, False

    def validate(self, finding: Finding, evidence_count: int) -> ValidationOutcome:
        return self._rules(finding, evidence_count)[0]

    async def validate_with_judge(
        self, finding: Finding, evidence_count: int
    ) -> tuple[ValidationOutcome, object | None]:
        """Validate with rules, refined by the optional LLM judge.

        Hard stops are returned immediately without consulting the judge. For
        softer cases the judge's verdict (when available) decides; otherwise the
        rule-based outcome stands (offline fallback). The verdict is returned so
        callers can persist the judge's reasoning and token/cost usage.
        """
        rule_outcome, is_hard_stop = self._rules(finding, evidence_count)
        if is_hard_stop or self.judge is None:
            return rule_outcome, None

        verdict = await self.judge.judge(finding, evidence_count)
        if verdict is None:
            return rule_outcome, None
        return verdict.outcome, verdict
