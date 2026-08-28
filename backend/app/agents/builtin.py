from __future__ import annotations

from typing import Any

from app.agents.base import BaseArchetype
from app.orchestration.hitl import consume, is_answered, is_approved
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

        # Human-in-the-Loop: a source-derived finding is flagged for review
        # before the run closes (resumes at justice).
        if findings and not is_answered(state):
            flagged = dict(findings[0], requires_human_review=True)
            update["findings"] = [*state.findings, flagged, *findings[1:], finding]
            approval = self._request_approval(
                state,
                kind="finding_review",
                context=f"Review candidate finding for {state.target.get('name', 'unknown')}.",
                proposal=flagged,
                next_node="justice",
            )
            update.update(approval)

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
        from app.core.security import is_devil_mode_enabled

        target = state.target.get("name", "unknown")

        # No destructive work when devil mode is not active (e.g. a pipeline
        # node reached out of scope) — just record a no-op.
        if not is_devil_mode_enabled(state.devil_mode):
            entry: dict[str, Any] = {
                "agent": self.key,
                "action": "noop",
                "mode": "simulate",
            }
            return {"history": [*state.history, entry]}

        # Human-in-the-Loop: destructive execution requires operator approval.
        # State machine over ``pending_review`` and the ``review_log``:
        #   A) no verdict yet     -> request approval and halt
        #   B) answered review    -> consume it, then execute (approved) or decline
        #   C) already approved   -> execute again (loop continues)
        #   D) already rejected   -> stay declined (never re-halt)
        was_answered = is_answered(state)
        consumed = consume(state) if was_answered else {}
        approved_logged = any(
            e.get("kind") == "destructive_action" and e.get("verdict") == "approved"
            for e in state.review_log
        )
        rejected_logged = any(
            e.get("kind") == "destructive_action" and e.get("verdict") == "rejected"
            for e in state.review_log
        )

        if was_answered and not is_approved(state):
            entry = {
                "agent": self.key,
                "action": "declined",
                "mode": "devil",
                "note": "Operator rejected the destructive action.",
            }
            return {
                **consumed,
                "stop_reason": "declined",
                "history": [*state.history, entry],
            }

        if not consumed and not approved_logged and not rejected_logged:
            approval = self._request_approval(
                state,
                kind="destructive_action",
                context=f"Executing an action against '{target}' (devil mode).",
                proposal={"agent": self.key, "role": self.role, "target": target},
                next_node=self.key,
            )
            approval["next_agent"] = self.key
            return approval

        if rejected_logged:
            entry = {
                "agent": self.key,
                "action": "declined",
                "mode": "devil",
                "note": "Operator rejected the destructive action.",
            }
            return {
                **consumed,
                "stop_reason": "declined",
                "history": [*state.history, entry],
            }

        result = await self._attempt(state, devil_mode=True)
        new_confidence = min(1.0, state.confidence + 0.4)

        finding = {
            "id": f"F-{len(state.findings) + 1}",
            "title": f"Executed action for {target}",
            "confidence": round(new_confidence, 2),
            "status": "candidate",
        }
        entry = {
            "agent": self.key,
            "action": "execute",
            "mode": "devil",
            "findings": 1,
        }
        update: dict[str, Any] = {
            **consumed,
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
