from __future__ import annotations

from pydantic import BaseModel


class ReviewCreate(BaseModel):
    approval_id: str
    approved: bool
    note: str | None = None
