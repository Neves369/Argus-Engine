from __future__ import annotations

import enum
from typing import Any

from pydantic import BaseModel, Field


class SourceKind(enum.StrEnum):
    HTTP = "http"
    CVE = "cve"


class DataSourceSpec(BaseModel):
    """Declarative description of an external data source provided by the operator.

    Sources are read-only information channels (CVE, OSINT, ...). Only the fields
    listed in ``fields`` are kept when normalizing a response (data minimization).
    """

    name: str
    description: str = ""
    kind: SourceKind = SourceKind.HTTP
    url: str | None = None
    method: str = "GET"
    params_template: dict[str, Any] = Field(default_factory=dict)
    timeout: float = 10.0
    rate_limit: float = 0.0
    ttl: int = 3600
    fields: list[str] = Field(default_factory=list)
