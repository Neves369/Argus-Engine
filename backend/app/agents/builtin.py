from __future__ import annotations

from typing import Any

from app.agents.base import BaseArchetype
from app.orchestration.state import GraphState


def _apply_llm(
    entry: dict[str, Any],
    update: dict[str, Any],
    state: GraphState,
    result,
    fallback_tokens: int,
) -> None:
    """Merge a gateway result into the node update, or degrade deterministically.

    When ``result`` is ``None`` (no API key / provider failure) the entry keeps
    the fixed simulation token count so offline runs behave as before.
    """
    if result is not None:
        entry["reasoning"] = result.content
        entry["decision"] = result.decision
        entry["tokens"] = result.usage.total_tokens
        entry["cost"] = result.usage.cost
        update["tokens_used"] = state.tokens_used + result.usage.total_tokens
        update["cost"] = round(state.cost + result.usage.cost, 6)
    else:
        entry["tokens"] = fallback_tokens
        update["tokens_used"] = state.tokens_used + fallback_tokens


class EmperorAgent(BaseArchetype):
    """Root node: plans the run and records the initial decision."""

    key = "emperor"
    name = "O Imperador"
    role = "director"
    model_tier = "strong"

    async def run(self, state: GraphState) -> dict:
        result = await self._attempt(state)
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "plan",
            "target": state.target.get("name", "unknown"),
            "scope": "authorized",
            "mode": "execute" if state.devil_mode else "simulate",
        }
        update: dict[str, Any] = {}
        _apply_llm(entry, update, state, result, fallback_tokens=0)
        update["history"] = [*state.history, entry]
        return update


class HermitAgent(BaseArchetype):
    """Investigation node: simulates collection and raises confidence."""

    key = "hermit"
    name = "O Eremita"
    role = "collector"
    model_tier = "balanced"
    allowed_tools = ("echo",)

    async def run(self, state: GraphState) -> dict:
        result = await self._attempt(state)
        new_confidence = min(1.0, state.confidence + 0.4)
        sources = await self._collect_sources(state)

        findings = []
        for idx, source in enumerate(sources):
            if source.get("status") != "ok":
                continue
            findings.append(
                {
                    "id": f"F-{len(state.findings) + idx + 1}",
                    "title": (
                        f"Signal from {source.get('source', 'source')} "
                        f"for {state.target.get('name', 'unknown')}"
                    ),
                    "confidence": round(new_confidence, 2),
                    "status": "candidate",
                }
            )

        finding = {
            "id": f"F-{len(state.findings) + len(findings) + 1}",
            "title": f"Candidate signal for {state.target.get('name', 'unknown')}",
            "confidence": round(new_confidence, 2),
            "status": "candidate",
        }
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "simulate",
            "findings": len(findings) + 1,
            "sources_consulted": len(sources),
        }
        update: dict[str, Any] = {
            "findings": [*state.findings, *findings, finding],
            "confidence": new_confidence,
            "sources": [*state.sources, *sources],
        }
        _apply_llm(entry, update, state, result, fallback_tokens=250)
        update["history"] = [*state.history, entry]
        return update


class FoolAgent(BaseArchetype):
    """Explorer node: proposes hypotheses without invasive actions."""

    key = "fool"
    name = "O Louco"
    role = "explorer"
    model_tier = "balanced"

    async def run(self, state: GraphState) -> dict:
        result = await self._attempt(state)
        sources = await self._collect_sources(state)
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "explore",
            "target": state.target.get("name", "unknown"),
            "sources_consulted": len(sources),
        }
        update: dict[str, Any] = {
            "sources": [*state.sources, *sources],
        }
        _apply_llm(entry, update, state, result, fallback_tokens=0)
        update["history"] = [*state.history, entry]
        return update


class ChariotAgent(BaseArchetype):
    """Execution node: reachable only when devil_mode is enabled."""

    key = "chariot"
    name = "O Carro"
    role = "executor"
    model_tier = "cheap"

    async def run(self, state: GraphState) -> dict:
        result = await self._attempt(state, devil_mode=True)
        new_confidence = min(1.0, state.confidence + 0.4)

        finding = {
            "id": f"F-{len(state.findings) + 1}",
            "title": f"Executed action for {state.target.get('name', 'unknown')}",
            "confidence": round(new_confidence, 2),
            "status": "candidate",
        }
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "execute",
            "mode": "devil",
            "findings": 1,
        }
        update: dict[str, Any] = {
            "findings": [*state.findings, finding],
            "confidence": new_confidence,
        }
        _apply_llm(entry, update, state, result, fallback_tokens=500)
        update["history"] = [*state.history, entry]
        return update


class MagicianAgent(BaseArchetype):
    """Synthesis node: aggregates evidence into a coherent summary."""

    key = "magician"
    name = "O Mago"
    role = "synthesizer"
    model_tier = "strong"

    async def run(self, state: GraphState) -> dict:
        result = await self._attempt(state)
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "synthesize",
            "findings": len(state.findings),
            "evidence": len(state.evidence),
            "sources": len(state.sources),
        }
        update: dict[str, Any] = {}
        _apply_llm(entry, update, state, result, fallback_tokens=0)
        update["history"] = [*state.history, entry]
        return update


class JusticeAgent(BaseArchetype):
    """Final node: validates the accumulated state and closes the run."""

    key = "justice"
    name = "A Justiça"
    role = "analyst"
    model_tier = "balanced"

    async def run(self, state: GraphState) -> dict:
        result = await self._attempt(state)
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "validate",
            "candidates": len(state.findings),
            "sources": len(state.sources),
        }
        update: dict[str, Any] = {
            "next_agent": None,
            "stop_reason": "completed",
        }
        _apply_llm(entry, update, state, result, fallback_tokens=0)
        update["history"] = [*state.history, entry]
        return update
