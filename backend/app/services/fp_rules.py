from __future__ import annotations

import re
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.models import Finding, FpRule

_WHITESPACE = re.compile(r"\s+")
_MIN_PATTERN_LENGTH = 4


def normalize_pattern(value: str | None) -> str | None:
    """Normalize a candidate pattern; returns ``None`` when it is unusable.

    Learned/manual rules are substring patterns over title + description, so a
    pattern must be long enough to be discriminating (guards against generic
    noise like a bare "info").
    """
    if not value:
        return None
    normalized = _WHITESPACE.sub(" ", value.strip().lower())
    if len(normalized) < _MIN_PATTERN_LENGTH:
        return None
    return normalized


class FpRuleStore:
    """Persists and manages false-positive signatures (local knowledge)."""

    async def list_rules(self, db: AsyncSession) -> Sequence[FpRule]:
        result = await db.scalars(
            select(FpRule).order_by(FpRule.created_at.desc())
        )
        return result.all()

    async def create_rule(
        self,
        db: AsyncSession,
        pattern: str,
        *,
        source: str = "manual",
        source_finding_id: int | None = None,
    ) -> FpRule:
        normalized = normalize_pattern(pattern)
        if normalized is None:
            raise ValueError("pattern is too short to be a useful false-positive rule")
        existing = await db.scalar(
            select(FpRule).where(FpRule.pattern == normalized)
        )
        if existing is not None:
            return existing
        rule = FpRule(
            pattern=normalized,
            enabled=True,
            source=source,
            source_finding_id=source_finding_id,
        )
        db.add(rule)
        await db.flush()
        await db.refresh(rule)
        return rule

    async def set_enabled(self, db: AsyncSession, rule_id: int, enabled: bool) -> FpRule | None:
        rule = await db.get(FpRule, rule_id)
        if rule is None:
            return None
        rule.enabled = enabled
        return rule

    async def delete_rule(self, db: AsyncSession, rule_id: int) -> bool:
        rule = await db.get(FpRule, rule_id)
        if rule is None:
            return False
        await db.delete(rule)
        return True

    async def learn_from_finding(self, db: AsyncSession, finding: Finding) -> FpRule | None:
        """Close the loop: a human-confirmed FP becomes a local-knowledge rule."""
        if not get_settings().fp_learning:
            return None
        return await self.create_rule(
            db,
            finding.title,
            source="learned",
            source_finding_id=finding.id,
        )

    async def enabled_patterns(self, db: AsyncSession) -> list[str]:
        result = await db.scalars(
            select(FpRule.pattern).where(FpRule.enabled.is_(True))
        )
        return list(result.all() or [])

    async def count_hits(self, db: AsyncSession, finding: Finding) -> None:
        """Increment ``hit_count`` for every enabled learned rule that matches."""
        haystack = " ".join(
            part for part in (finding.title, finding.description or "") if part
        ).lower()
        rules = await db.scalars(
            select(FpRule).where(FpRule.enabled.is_(True), FpRule.source == "learned")
        )
        for rule in rules.all():
            if rule.pattern in haystack:
                rule.hit_count += 1