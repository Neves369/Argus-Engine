from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TargetBase(BaseModel):
    name: str
    url: str | None = None
    notes: str | None = None


class TargetCreate(TargetBase):
    pass


class TargetRead(TargetBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
