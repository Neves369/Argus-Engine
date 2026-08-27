from __future__ import annotations

from pydantic import BaseModel


class Health(BaseModel):
    status: str
    app: str
    version: str = "0.1.0"
