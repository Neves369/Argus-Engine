from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CompositionCreate(BaseModel):
    name: str
    archetypes: list[str]
    target: dict[str, Any] | None = None
    devil_mode: bool = False


class CompositionExecute(BaseModel):
    pass


class CompositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    target_id: int | None
    status: str
    config: dict[str, Any] | None
    created_at: datetime
