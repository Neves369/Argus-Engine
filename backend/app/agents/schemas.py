"""Mandatory output schema per archetype (Etapa 2).

Every archetype declares an ``output_schema`` (a Pydantic model) describing the
shape of the ``history``/trace entry its ``run()`` produces. ``BaseArchetype``
validates each entry against this schema before it is appended to
``GraphState.history`` (see ``BaseArchetype.validate_entry``), so a code change
that silently drops or renames a field breaks a test immediately instead of
corrupting downstream consumers (dashboard, exports, judge, HITL).

Fields common to every LLM-backed node (``reasoning``, ``decision``, token/cost
breakdown, ``provider``/``model``/``strategy``) are declared once on
``ArchetypeOutputBase`` as optional: they are only present when the gateway
call succeeded (see ``app.agents.builtin._apply_llm``); offline/simulated runs
omit them and still validate.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict


class ArchetypeOutputBase(BaseModel):
    """Fields shared by every archetype's history entry.

    ``extra="allow"`` keeps this schema forward-compatible with additional
    diagnostic fields an archetype may add, while still enforcing the fields
    declared explicitly (here and in subclasses) as the required contract.
    """

    model_config = ConfigDict(extra="allow")

    agent: str
    action: str

    # Present only when the LLM gateway produced a real completion for this
    # node (see ``_apply_llm``); absent on offline/deterministic fallback.
    reasoning: str | None = None
    decision: dict[str, Any] | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost: float | None = None
    provider: str | None = None
    model: str | None = None
    strategy: str | None = None


class EmperorOutput(ArchetypeOutputBase):
    """Director node: plans the run."""

    action: Literal["plan"]
    target: str
    scope: str
    mode: Literal["execute", "simulate"]
    tokens: int


class HermitOutput(ArchetypeOutputBase):
    """Collector node: gathers signal from configured sources."""

    action: Literal["simulate"]
    findings: int
    sources_consulted: int
    tokens: int


class FoolOutput(ArchetypeOutputBase):
    """Explorer node: raises hypotheses without invasive action."""

    action: Literal["explore"]
    target: str
    sources_consulted: int
    tokens: int


class ChariotOutput(ArchetypeOutputBase):
    """Execution node.

    Fields are optional beyond ``agent``/``action``/``mode`` because the
    branch taken depends on the HITL approval state at call time: a ``noop``
    (devil mode off) or ``declined`` (operator rejected) entry never reaches
    the LLM gateway or produces findings, while ``execute`` always does.
    """

    action: Literal["noop", "declined", "execute"]
    mode: Literal["simulate", "devil"]
    note: str | None = None
    findings: int | None = None
    tokens: int | None = None


class MagicianOutput(ArchetypeOutputBase):
    """Synthesis node: aggregates evidence into a summary."""

    action: Literal["synthesize"]
    findings: int
    evidence: int
    sources: int
    tokens: int


class JusticeOutput(ArchetypeOutputBase):
    """Final node: validates accumulated state and closes the run."""

    action: Literal["validate"]
    candidates: int
    sources: int
    tokens: int


__all__ = [
    "ArchetypeOutputBase",
    "ChariotOutput",
    "EmperorOutput",
    "FoolOutput",
    "HermitOutput",
    "JusticeOutput",
    "MagicianOutput",
]
