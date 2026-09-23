from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class RunCreate(BaseModel):
    target_id: int | None = None
    target: dict[str, Any] | None = None
    devil_mode: bool = False
    archetypes: list[str] | None = None
    depth: Literal["quick", "deep"] = "quick"
    probe_classes: list[str] | None = None
    journey_classes: list[str] | None = None
    #: Pacote de política (M10-P0): quando definido, é autoritativo para
    #: depth/probe_classes/journey_classes/devil_mode do run (valores explícitos
    #: do payload são ignorados em favor do pacote versionado).
    policy_package: str | None = None
    #: Preset Tarot (M10-P3): composição pronta de cartas. Quando definido,
    #: é autoritativo para ``archetypes`` e pode sugerir um ``policy_package``
    #: (um ``policy_package`` explícito no payload vence o do preset).
    preset: str | None = None


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
