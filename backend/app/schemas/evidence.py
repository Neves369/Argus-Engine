from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class EvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    finding_id: int | None
    run_id: int | None
    file_name: str
    file_path: str
    sha256: str
    size: int
    mime: str | None
    created_at: datetime
