from __future__ import annotations

from pydantic import BaseModel


class PolicyRead(BaseModel):
    version: str
    sha256: str
    text: str
