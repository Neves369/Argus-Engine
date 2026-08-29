from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.finding import FindingStatus


class FindingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    target_id: int | None
    title: str
    description: str | None
    severity: str | None
    category: str | None
    affected: str | None
    cvss_score: float | None
    cvss_vector: str | None
    cves: list | None
    known_exploits: list | None
    remediation: str | None
    references: list | None
    confidence: float
    status: str
    score: float | None
    requires_human_review: bool
    validated_at: datetime | None
    meta: dict | None
    created_at: datetime
    updated_at: datetime


class FindingUpdate(BaseModel):
    status: FindingStatus
