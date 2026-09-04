from __future__ import annotations

from app.db.models import Finding


class FalsePositiveBlacklist:
    """Matches findings against known false-positive signatures (local knowledge)."""

    def __init__(self, patterns: list[str] | None = None) -> None:
        self._patterns = [pattern.lower() for pattern in (patterns or []) if pattern]

    def matches(self, finding: Finding) -> bool:
        haystack = " ".join(
            part for part in (finding.title, finding.description or "") if part
        ).lower()
        return any(pattern in haystack for pattern in self._patterns)
