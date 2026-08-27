from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class GraphState(BaseModel):
    """Shared, typed state passed between graph nodes.

    Serializable by design so a run can be persisted and resumed.
    """

    target: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)

    tokens_used: int = 0
    cost: float = 0.0

    budget_tokens: int = 100_000
    budget_cost: float = 1.0

    confidence: float = 0.0
    stop_reason: str | None = None
    next_agent: str | None = None
