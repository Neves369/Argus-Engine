from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.services.fp_rules import normalize_pattern


class FpRuleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pattern: str
    enabled: bool
    source: str
    source_finding_id: int | None
    hit_count: int
    created_at: datetime
    updated_at: datetime


class FpRuleCreate(BaseModel):
    pattern: str

    @field_validator("pattern")
    @classmethod
    def _must_be_usable(cls, value: str) -> str:
        normalized = normalize_pattern(value)
        if normalized is None:
            raise ValueError("pattern is too short to be a useful false-positive rule")
        return normalized


class FpRuleUpdate(BaseModel):
    enabled: bool