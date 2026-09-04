from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.agents.base import BaseArchetype
from app.agents.schemas import (
    ChariotOutput,
    EmperorOutput,
    FoolOutput,
    HermitOutput,
    JusticeOutput,
    MagicianOutput,
)
from app.orchestration.hitl import consume, is_answered, is_approved
from app.orchestration.state import GraphState
from app.services.source_findings import derive_findings_from_sources


def _utcnow() -> datetime:
    return datetime.now(UTC)


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

    Also accumulates per-agent totals (``tokens_by_agent``/``cost_by_agent``,
    keyed by ``entry["agent"]``) alongside the run-wide totals, so a
    per-agent budget cap (``settings.budget_tokens_per_agent``) can be
    enforced independently of the run-wide one — see `should_continue`.
    """
    agent_key = entry["agent"]
    if result is not None:
        entry["reasoning"] = result.content
        entry["decision"] = result.decision
        entry["tokens"] = result.usage.total_tokens
        entry["prompt_tokens"] = result.usage.prompt_tokens
        entry["completion_tokens"] = result.usage.completion_tokens
        entry["cost"] = result.usage.cost
        entry["provider"] = result.provider
        entry["model"] = result.model
        entry["strategy"] = result.strategy
        added_tokens = result.usage.total_tokens
        added_cost = result.usage.cost
        update["cost"] = round(state.cost + added_cost, 6)
    else:
        entry["tokens"] = fallback_tokens
        added_tokens = fallback_tokens
        added_cost = 0.0
        # No real cost incurred offline — leave `cost` out of the update
        # entirely (unchanged) rather than echoing back the same value.

    update["tokens_used"] = state.tokens_used + added_tokens
    update["tokens_by_agent"] = {
        **state.tokens_by_agent,
        agent_key: state.tokens_by_agent.get(agent_key, 0) + added_tokens,
    }
    if added_cost:
        update["cost_by_agent"] = {
            **state.cost_by_agent,
            agent_key: round(state.cost_by_agent.get(agent_key, 0.0) + added_cost, 6),
        }


class EmperorAgent(BaseArchetype):
    """Root node: plans the run and records the initial decision."""

    key = "emperor"
    name = "O Imperador"
    role = "director"
    model_tier = "strong"
    output_schema = EmperorOutput

    def system_prompt(self) -> str:
        return (
            "You are O Imperador, the director/orchestrator archetype. "
            "You open the run: state the authorized target and scope, then set a "
            "short, high-level plan for what the other archetypes should establish "
            "(what to investigate, in what order). "
            "Operate only within the authorized scope declared for this run. "
            "Never propose or describe reconnaissance techniques, exploitation "
            "steps, payloads, or tool chaining — that is out of your role. "
            "Be concise and factual; a few sentences is enough."
        )

    async def run(self, state: GraphState) -> dict:
        started_at = _utcnow()
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
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(self._trace_update(state, entry, started_at))
        return update


class HermitAgent(BaseArchetype):
    """Investigation node: simulates collection and raises confidence."""

    key = "hermit"
    name = "O Eremita"
    role = "collector"
    model_tier = "balanced"
    allowed_tools = ("echo",)
    output_schema = HermitOutput

    def system_prompt(self) -> str:
        return (
            "You are O Eremita, the collector/investigator archetype. "
            "You gather and summarize information already made available through "
            "configured, read-only data sources (e.g. normalized OSINT/CVE feeds) — "
            "you do not query anything outside what the platform provides. "
            "Summarize what was found and how it affects confidence in the current "
            "investigation, in plain factual terms. "
            "Never describe reconnaissance methods, scanning techniques, or how "
            "to obtain information outside the provided sources — that is out of "
            "your role. Be concise."
        )

    async def run(self, state: GraphState) -> dict:
        started_at = _utcnow()
        result = await self._attempt(state)
        new_confidence = min(1.0, state.confidence + 0.4)
        sources = await self._collect_sources(state)
        target = state.target.get("name", "unknown")

        # The hermit node loops until the confidence threshold is met; dedupe
        # by title against findings already recorded (a subsequent pass may
        # re-derive the same lead from a cached source result).
        existing_titles = {f.get("title") for f in state.findings}
        derived = derive_findings_from_sources(target, sources)
        findings = []
        for finding in derived:
            if finding["title"] in existing_titles:
                continue
            finding["id"] = f"F-{len(state.findings) + len(findings) + 1}"
            findings.append(finding)

        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "simulate",
            "findings": len(findings),
            "sources_consulted": len(sources),
        }
        update: dict[str, Any] = {
            "findings": [*state.findings, *findings],
            "confidence": new_confidence,
            "sources": [*state.sources, *sources],
        }
        _apply_llm(entry, update, state, result, fallback_tokens=250)
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(self._trace_update(state, entry, started_at, confidence_after=new_confidence))

        return update


class FoolAgent(BaseArchetype):
    """Explorer node: proposes hypotheses without invasive actions."""

    key = "fool"
    name = "O Louco"
    role = "explorer"
    model_tier = "balanced"
    output_schema = FoolOutput

    def system_prompt(self) -> str:
        return (
            "You are O Louco, the explorer archetype. "
            "You propose hypotheses worth investigating further, based only on "
            "publicly-observable, non-invasive signals already surfaced by other "
            "nodes or configured sources. Frame hypotheses, not conclusions. "
            "Never propose or describe an actual test, probe, or exploitation "
            "step — hand that decision to the human operator. Be concise."
        )

    async def run(self, state: GraphState) -> dict:
        started_at = _utcnow()
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
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(self._trace_update(state, entry, started_at))
        return update


class ChariotAgent(BaseArchetype):
    """Execution node: reachable only when devil_mode is enabled."""

    key = "chariot"
    name = "O Carro"
    role = "executor"
    model_tier = "cheap"
    output_schema = ChariotOutput

    def system_prompt(self) -> str:
        return (
            "You are O Carro, the controlled-execution archetype. "
            "You only act when the run is explicitly in execution mode AND a "
            "human operator has approved this specific action against the "
            "authorized target — never on your own initiative. "
            "Your response is a short factual record of the action taken and its "
            "outcome, for the audit log — not a description of how it was done. "
            "Never include technique detail, payload content, or step-by-step "
            "instructions of any kind."
        )

    async def run(self, state: GraphState) -> dict:
        from app.core.security import is_devil_mode_enabled

        started_at = _utcnow()
        target = state.target.get("name", "unknown")

        # No destructive work when devil mode is not active (e.g. a pipeline
        # node reached out of scope) — just record a no-op.
        if not is_devil_mode_enabled(state.devil_mode):
            entry: dict[str, Any] = self.validate_entry(
                {
                    "agent": self.key,
                    "action": "noop",
                    "mode": "simulate",
                }
            )
            update = {"history": [*state.history, entry]}
            update.update(self._trace_update(state, entry, started_at))
            return update

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
            entry = self.validate_entry(
                {
                    "agent": self.key,
                    "action": "declined",
                    "mode": "devil",
                    "note": "Operator rejected the destructive action.",
                }
            )
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
            entry = self.validate_entry(
                {
                    "agent": self.key,
                    "action": "declined",
                    "mode": "devil",
                    "note": "Operator rejected the destructive action.",
                }
            )
            return {
                **consumed,
                "stop_reason": "declined",
                "history": [*state.history, entry],
            }

        result = await self._attempt(state, devil_mode=True)

        # Argus Engine ships without a real destructive-execution backend by
        # design (see ROADMAP/ADR on Devil Mode scope) — the action IS
        # approved at this point, but there is nothing real to run. Report
        # that honestly instead of fabricating a success record: a security
        # tool's audit trail must never claim an action happened when it
        # didn't.
        entry = {
            "agent": self.key,
            "action": "no_backend",
            "mode": "devil",
            "note": (
                "Ação aprovada pelo operador, mas nenhum backend de execução "
                "real está configurado nesta instância — nada foi executado."
            ),
            "findings": 0,
        }
        update: dict[str, Any] = {**consumed, "stop_reason": "no_backend"}
        _apply_llm(entry, update, state, result, fallback_tokens=0)
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(self._trace_update(state, entry, started_at))
        return update


class MagicianAgent(BaseArchetype):
    """Synthesis node: aggregates evidence into a coherent summary."""

    key = "magician"
    name = "O Mago"
    role = "synthesizer"
    model_tier = "strong"
    output_schema = MagicianOutput

    def system_prompt(self) -> str:
        return (
            "You are O Mago, the synthesis archetype. "
            "You combine the findings, evidence, and consulted sources gathered "
            "so far into a coherent, plain-language summary of the current state "
            "of the investigation — what is known, and how confident we are. "
            "Do not introduce new findings or speculate beyond what other nodes "
            "already recorded. Never include technique or exploitation detail. "
            "Be concise."
        )

    async def run(self, state: GraphState) -> dict:
        started_at = _utcnow()
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
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(self._trace_update(state, entry, started_at))
        return update


class JusticeAgent(BaseArchetype):
    """Final node: validates the accumulated state and closes the run."""

    key = "justice"
    name = "A Justiça"
    role = "analyst"
    model_tier = "balanced"
    output_schema = JusticeOutput

    def system_prompt(self) -> str:
        return (
            "You are A Justiça, the validator/analyst archetype. "
            "You are the mandatory final node of every graph: review the "
            "candidate findings and sources accumulated during the run, and give "
            "a short, factual closing assessment of how well-supported they are. "
            "You do not decide pass/fail on individual findings — that is the "
            "quality-filter pipeline's job — you summarize for the audit record. "
            "Never include technique or exploitation detail. Be concise."
        )

    async def run(self, state: GraphState) -> dict:
        started_at = _utcnow()
        result = await self._attempt(state)
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "validate",
            "candidates": len(state.findings),
            "sources": len(state.sources),
        }
        # Preserva uma razão de parada final já definida (ex.: estouro de
        # orçamento em should_continue); não herda "pending_review" de uma
        # parada HITL anterior — o nó final sempre encerra como "completed".
        if state.stop_reason in ("budget", "agent_budget", "confidence", "declined", "no_backend"):
            final_reason = state.stop_reason
        else:
            final_reason = "completed"
        update: dict[str, Any] = {
            "next_agent": None,
            "stop_reason": final_reason,
        }
        _apply_llm(entry, update, state, result, fallback_tokens=0)
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(self._trace_update(state, entry, started_at))
        return update
