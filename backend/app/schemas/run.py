from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class RunCreate(BaseModel):
    target_id: int | None = None
    target: dict[str, Any] | None = None
    devil_mode: bool = False
    archetypes: list[str] | None = None


class RunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    target_id: int | None
    status: str
    result: dict[str, Any] | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
