from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class ToolKind(enum.StrEnum):
    HTTP = "http"
    CLI = "cli"


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    kind: ToolKind = ToolKind.CLI
    params: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    timeout: float = 10.0
    rate_limit: float = 0.0
    destructive: bool = False
    url: str | None = None
    method: str = "GET"
    command: str | None = None
    # Sandbox Docker (Etapa 5): overrides opcionais da policy do executor.
    sandbox_image: str | None = None
    sandbox_network: bool = False
    sandbox_user: str | None = None
