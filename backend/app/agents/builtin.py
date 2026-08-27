from __future__ import annotations

from app.agents.base import BaseArchetype
from app.orchestration.state import GraphState


class EmperorAgent(BaseArchetype):
    """Root node: plans the run and records the initial decision."""

    key = "emperor"
    name = "O Imperador"
    role = "director"
    model_tier = "strong"

    async def run(self, state: GraphState) -> dict:
        entry = {
            "agent": self.key,
            "action": "plan",
            "target": state.target.get("name", "unknown"),
            "scope": "authorized",
            "mode": "execute" if state.devil_mode else "simulate",
        }
        return {"history": [*state.history, entry]}


class HermitAgent(BaseArchetype):
    """Investigation node: simulates collection and raises confidence."""

    key = "hermit"
    name = "O Eremita"
    role = "collector"
    model_tier = "balanced"
    allowed_tools = ("echo",)

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
            "action": "simulate",
            "tokens": 250,
            "findings": 1,
        }
        return {
            "findings": [*state.findings, finding],
            "history": [*state.history, entry],
            "tokens_used": new_tokens,
            "confidence": new_confidence,
        }


class FoolAgent(BaseArchetype):
    """Explorer node: proposes hypotheses without invasive actions."""

    key = "fool"
    name = "O Louco"
    role = "explorer"
    model_tier = "balanced"

    async def run(self, state: GraphState) -> dict:
        entry = {
            "agent": self.key,
            "action": "explore",
            "target": state.target.get("name", "unknown"),
        }
        return {"history": [*state.history, entry]}


class ChariotAgent(BaseArchetype):
    """Execution node: reachable only when devil_mode is enabled."""

    key = "chariot"
    name = "O Carro"
    role = "executor"
    model_tier = "cheap"

    async def run(self, state: GraphState) -> dict:
        new_tokens = state.tokens_used + 500
        new_confidence = min(1.0, state.confidence + 0.4)

        finding = {
            "id": f"F-{len(state.findings) + 1}",
            "title": f"Executed action for {state.target.get('name', 'unknown')}",
            "confidence": round(new_confidence, 2),
            "status": "candidate",
        }
        entry = {
            "agent": self.key,
            "action": "execute",
            "mode": "devil",
            "tokens": 500,
            "findings": 1,
        }
        return {
            "findings": [*state.findings, finding],
            "history": [*state.history, entry],
            "tokens_used": new_tokens,
            "confidence": new_confidence,
        }


class MagicianAgent(BaseArchetype):
    """Synthesis node: aggregates evidence into a coherent summary."""

    key = "magician"
    name = "O Mago"
    role = "synthesizer"
    model_tier = "strong"

    async def run(self, state: GraphState) -> dict:
        entry = {
            "agent": self.key,
            "action": "synthesize",
            "findings": len(state.findings),
            "evidence": len(state.evidence),
        }
        return {"history": [*state.history, entry]}


class JusticeAgent(BaseArchetype):
    """Final node: validates the accumulated state and closes the run."""

    key = "justice"
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
