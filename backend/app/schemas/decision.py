from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DecisionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    agent: str
    action: str
    detail: dict[str, Any] | None
    created_at: datetime
