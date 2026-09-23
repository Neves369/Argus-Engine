from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class CompositionCreate(BaseModel):
    name: str
    archetypes: list[str]
    target: dict[str, Any] | None = None
    devil_mode: bool = False
    depth: Literal["quick", "deep"] = "quick"
    probe_classes: list[str] | None = None
    journey_classes: list[str] | None = None
    #: Pacote de política (M10-P0): autoritativo quando definido (ver RunCreate).
    policy_package: str | None = None
    #: Preset Tarot (M10-P3): composição pronta de cartas (ver RunCreate).
    preset: str | None = None


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
