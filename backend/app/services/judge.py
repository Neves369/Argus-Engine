"""LLM judge that refines rule-based validation of findings.

The judge consults the LLM gateway (judgment pool) to assess whether a
candidate finding is a real, exploitable signal or a false positive. It never
overrides the safety guards of the pipeline (blacklist and high severity);
those remain hard rules in ``ValidationPipeline``.

When the gateway is unavailable (no API key) or the model returns an unusable
verdict, the judge yields ``None`` so callers degrade to rule-based scoring.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.db.models import Finding
from app.llm.router import attempt_completion
from app.services.quality import ValidationOutcome

_OUTCOMES = {item.value for item in ValidationOutcome}


@dataclass(frozen=True)
class JudgeVerdict:
    outcome: ValidationOutcome
    reason: str
    tokens: int = 0
    cost: float = 0.0
    model: str | None = None
    provider: str | None = None


def _parse_outcome(raw: str | None) -> ValidationOutcome | None:
    if not raw:
        return None
    normalized = raw.strip().lower()
    if normalized not in _OUTCOMES:
        return None
    return ValidationOutcome(normalized)


def _extract_verdict(content: str) -> dict | None:
    """Extract the JSON verdict object from the completion text."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    candidate = None
    if fenced:
        candidate = fenced.group(1)
    else:
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if match:
            candidate = match.group(0)
    if not candidate:
        return None
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class LLMJudge:
    """Assesses a candidate finding using the LLM gateway (judgment pool)."""

    async def judge(self, finding: Finding, evidence_count: int) -> JudgeVerdict | None:
        system = (
            "You are an impartial validator of security findings. Judge whether a "
            "candidate finding is plausible or a false positive based only on the "
            "given evidence count and description. Respond with JSON only: "
            '{"outcome": "validate" | "false_positive" | "needs_review", '
            '"reason": "<short reason>"}. Never discuss techniques or exploits.'
        )
        user = (
            f"Title: {finding.title}\n"
            f"Description: {finding.description or ''}\n"
            f"Severity: {finding.severity or 'unspecified'}\n"
            f"Confidence: {finding.confidence:.2f}\n"
            f"Evidence count: {evidence_count}\n"
            "Is this a genuine finding or a false positive?"
        )

        result = await attempt_completion(system, user, devil_mode=False)
        if result is None:
            return None

        data = _extract_verdict(result.content)
        if data is None:
            return None

        outcome = _parse_outcome(data.get("outcome"))
        if outcome is None:
            return None

        return JudgeVerdict(
            outcome=outcome,
            reason=str(data.get("reason", "") or "")[:300],
            tokens=result.usage.total_tokens,
            cost=result.usage.cost,
            model=result.model,
            provider=result.provider,
        )
