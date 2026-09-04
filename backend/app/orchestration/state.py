from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr


class GraphState(BaseModel):
    """Shared, typed state passed between graph nodes.

    Serializable by design so a run can be persisted and resumed.
    """

    target: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)

    tokens_used: int = 0
    cost: float = 0.0

    #: Per-agent totals, keyed by archetype key (e.g. "hermit"). Only
    #: meaningful for archetypes that can loop (hermit/chariot in the default
    #: pipeline) — a custom pipeline runs each archetype once, so its own
    #: total is just that single call's usage. See `budget_tokens_per_agent`
    #: in settings and `should_continue` in `app.orchestration.graph`.
    tokens_by_agent: dict[str, int] = Field(default_factory=dict)
    cost_by_agent: dict[str, float] = Field(default_factory=dict)

    budget_tokens: int = 100_000
    budget_cost: float = 1.0

    confidence: float = 0.0
    stop_reason: str | None = None
    next_agent: str | None = None

    devil_mode: bool = False

    # Human-in-the-loop: a run awaiting operator approval halts here.
    pending_review: dict[str, Any] | None = None
    human_decision: dict[str, Any] | None = None
    review_log: list[dict[str, Any]] = Field(default_factory=list)
    human_gate_next: str | None = None

    # Runtime-only injectable (not serialized): lets agents query data sources.
    _sources_service: Any = PrivateAttr(default=None)

    @property
    def sources_service(self) -> Any:
        return self._sources_service

    def set_sources_service(self, service: Any) -> None:
        self._sources_service = service
