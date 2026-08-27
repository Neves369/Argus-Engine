from __future__ import annotations

from app.agents.base import BaseArchetype
from app.orchestration.state import GraphState


class DirectorAgent(BaseArchetype):
    """Root node: plans the run and records the initial decision."""

    key = "director"
    name = "O Imperador"
    role = "director"
    model_tier = "strong"

    async def run(self, state: GraphState) -> dict:
        entry = {
            "agent": self.key,
            "action": "plan",
            "target": state.target.get("name", "unknown"),
            "scope": "authorized",
        }
        return {
            "history": [*state.history, entry],
            "next_agent": "collector",
        }


class CollectorAgent(BaseArchetype):
    """Placeholder node that accumulates a candidate signal and raises confidence."""

    key = "collector"
    name = "O Eremita"
    role = "collector"
    model_tier = "balanced"

    async def run(self, state: GraphState) -> dict:
        new_tokens = state.tokens_used + 250
        new_confidence = min(1.0, state.confidence + 0.4)

        finding = {
            "id": f"F-{len(state.findings) + 1}",
            "title": f"Candidate signal for {state.target.get('name', 'unknown')}",
            "confidence": round(new_confidence, 2),
            "status": "candidate",
        }
        entry = {
            "agent": self.key,
            "action": "collect",
            "tokens": 250,
            "findings": 1,
        }
        return {
            "findings": [*state.findings, finding],
            "history": [*state.history, entry],
            "tokens_used": new_tokens,
            "confidence": new_confidence,
        }


class AnalystAgent(BaseArchetype):
    """Final node: validates the accumulated state and closes the run."""

    key = "analyst"
    name = "A Justiça"
    role = "analyst"
    model_tier = "balanced"

    async def run(self, state: GraphState) -> dict:
        entry = {
            "agent": self.key,
            "action": "validate",
            "candidates": len(state.findings),
        }
        return {
            "history": [*state.history, entry],
            "next_agent": None,
            "stop_reason": "completed",
        }
