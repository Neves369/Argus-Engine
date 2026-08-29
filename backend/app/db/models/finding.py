from __future__ import annotations

import enum
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def _utcnow() -> datetime:
    return datetime.now(UTC)


class FindingStatus(enum.StrEnum):
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    FALSE_POSITIVE = "false_positive"
    DISCARDED = "discarded"


ALLOWED_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.CANDIDATE: {FindingStatus.FALSE_POSITIVE, FindingStatus.DISCARDED},
    FindingStatus.VALIDATED: {FindingStatus.FALSE_POSITIVE, FindingStatus.DISCARDED},
    FindingStatus.FALSE_POSITIVE: set(),
    FindingStatus.DISCARDED: set(),
}


class Finding(Base):
    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True, index=True)
    target_id: Mapped[int | None] = mapped_column(
        ForeignKey("targets.id"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    affected: Mapped[str | None] = mapped_column(String(512), nullable=True)
    cvss_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    cvss_vector: Mapped[str | None] = mapped_column(String(128), nullable=True)
    cves: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    known_exploits: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    remediation: Mapped[str | None] = mapped_column(Text, nullable=True)
    references: Mapped[list[Any] | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default=FindingStatus.CANDIDATE.value, nullable=False, index=True
    )
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    requires_human_review: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
