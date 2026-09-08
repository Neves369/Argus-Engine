from __future__ import annotations

import asyncio
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
from app.core.config import get_settings
from app.orchestration.hitl import consume, is_answered, is_approved
from app.orchestration.state import GraphState
from app.scanning.service import ScanBlockedError, ScanReport
from app.services.scan_findings import derive_findings_from_scan
from app.services.source_findings import derive_findings_from_sources
from app.tools.executor import ToolExecutor
from app.tools.spec import ToolKind


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _agent_over_budget(settings: Any, agent: str, state: GraphState) -> bool:
    """True quando o agente igualou/ultrapassou o orçamento per-agente.

    Ambos os tetos desligados (0) significam "sem limite". Usado pelo
    Imperador para nunca delegar um membro que já esgotou o próprio teto.
    """
    if settings.budget_tokens_per_agent > 0:
        if state.tokens_by_agent.get(agent, 0) >= settings.budget_tokens_per_agent:
            return True
    if settings.budget_cost_per_agent > 0:
        if state.cost_by_agent.get(agent, 0.0) >= settings.budget_cost_per_agent:
            return True
    return False


async def _correlate_cves(
    state: GraphState, report: ScanReport
) -> list[dict[str, Any]]:
    """Best-effort CVE/KEV correlation of a scan report (never raises)."""
    if state.sources_service is None or not (report.pages or []):
        return []
    from app.services.cve_correlate import correlate_scan_report

    try:
        return await correlate_scan_report(report, state.sources_service)
    except Exception:  # noqa: BLE001 - correlation must never break the run
        return []


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
    enforced independently of the run-wide one — o Imperador respeita o teto
    ao delegar (`EmperorAgent`).
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
    """Root node: plans the run and supervises the team sequentially."""

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
            "On later calls you decide the next agent to run and may close the run. "
            "Operate only within the authorized scope declared for this run. "
            "Never propose or describe reconnaissance techniques, exploitation "
            "steps, payloads, or tool chaining — that is out of your role. "
            "Be concise and factual; a few sentences is enough. "
            "When you decide the next agent, output a JSON object at the end of "
            "your response with two fields: {\"next_agent\": \"<agent_key>\" "
            "(must be one of the available agents: {team_list}), \"objective\": \"<short>\"}. "
            "If you want to close the run, output {\"next_agent\": null}. "
            "If the API is unavailable, degrade deterministically: pick the first "
            "available agent or close after one full round."
        ).replace("{team_list}", ", ".join(("hermit", "fool", "magician", "chariot")))

    async def run(self, state: GraphState) -> dict:
        started_at = _utcnow()
        from app.core.config import get_settings

        settings = get_settings()
        max_rounds = settings.supervisor_max_rounds

        # Determine if this is the first emperor call (no prior emperor entries).
        emperor_entries = [
            e for e in state.history if e.get("agent") == self.key
        ]
        first_call = len(emperor_entries) == 0

        result = await self._attempt(state)

        # Base entry fields common to all actions.
        entry: dict[str, Any] = {
            "agent": self.key,
            "target": state.target.get("name", "unknown"),
            "scope": "authorized",
            "mode": "execute" if state.devil_mode else "simulate",
        }

        if first_call:
            # --- PLAN phase: first Emperor call. Delegate to first team member.
            entry["action"] = "plan"
            # Set deterministic fallback for delegation.
            if state.team:
                chosen = state.team[0]
            else:
                chosen = None
            state.delegate_to = chosen
            entry["next_agent"] = chosen
            entry["objective"] = "Iniciar investigação com o agente escolhido."
            # LLM may suggest a different agent or objective; try to parse.
            if result is not None and result.content:
                parsed = self._parse_next_agent(result.content)
                if parsed and parsed.get("next_agent") and parsed["next_agent"] in state.team:
                    chosen = parsed["next_agent"]
                    state.delegate_to = chosen
                    entry["next_agent"] = chosen
                if parsed and parsed.get("objective"):
                    entry["objective"] = parsed["objective"]
            # If offline or parse failed, keep deterministic choice.
            # Register the plan entry.
        else:
            # --- DIRECT or CLOSE phase: subsequent Emperor calls.
            # Check stop conditions first — confiança suficiente é decisão do
            # supervisor: quando o time já produziu o suficiente, fecha em vez
            # de delegar mais uma vez.
            confident = state.confidence >= settings.confidence_threshold
            over_rounds = state.supervisor_rounds >= max_rounds
            team_empty = len(state.team) == 0
            all_delegated = (
                state.delegate_to is not None and state.delegate_to not in state.team
            )

            if confident or over_rounds or all_delegated or team_empty:
                # Close the run → route to Justice.
                entry["action"] = "close"
                state.delegate_to = None
                entry["next_agent"] = None
                entry["objective"] = "Fechamento solicitado pelo Imperador."
            else:
                # Direct: choose next agent.
                parsed = None
                if result is not None and result.content:
                    parsed = self._parse_next_agent(result.content)

                # O LLM pode fechar explicitamente ({next_agent: null}).
                if parsed is not None and parsed.get("next_agent") is None:
                    entry["action"] = "close"
                    state.delegate_to = None
                    entry["next_agent"] = None
                    entry["objective"] = "Fechamento solicitado pelo Imperador."
                else:
                    # Try parsed choice; validate it belongs to the team.
                    chosen = None
                    if parsed and parsed.get("next_agent") in state.team:
                        chosen = parsed["next_agent"]
                    else:
                        # Deterministic fallback: advance to next unused member.
                        if state.delegate_to is None:
                            # First direct after plan: start with team[0].
                            chosen = state.team[0] if state.team else None
                        else:
                            # Rotate: find next member after the current delegate.
                            try:
                                idx = state.team.index(state.delegate_to)
                                next_idx = (idx + 1) % len(state.team)
                                chosen = state.team[next_idx]
                            except ValueError:
                                chosen = state.team[0] if state.team else None

                    if chosen is not None:
                        # Orçamento por agente: nunca delega um membro que já
                        # igualou/ultrapassou o próprio teto (`budget_tokens_
                        # per_agent`/`budget_cost_per_agent`, 0 = desligado).
                        # Rotaciona para o próximo sob o teto; se ninguém tiver
                        # folga, fecha por "agent_budget".
                        if _agent_over_budget(settings, chosen, state):
                            alternates = [
                                m
                                for m in state.team
                                if not _agent_over_budget(settings, m, state)
                            ]
                            chosen = alternates[0] if alternates else None
                            if chosen is None:
                                state.stop_reason = "agent_budget"

                    if chosen is not None:
                        state.delegate_to = chosen
                        entry["action"] = "direct"
                        entry["next_agent"] = chosen
                        # Advance round counter only when we actually delegate.
                        state.supervisor_rounds += 1
                    else:
                        # No team members left, or all over their per-agent cap;
                        # close instead.
                        entry["action"] = "close"
                        state.delegate_to = None
                        entry["next_agent"] = None

        # --- Apply LLM result into entry (tokens, cost, etc.) ---
        update: dict[str, Any] = {}
        _apply_llm(entry, update, state, result, fallback_tokens=0)

        # Validate the entry against EmperorOutput schema.
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        # Campos do supervisor precisam persistir no estado (mutações in-place
        # de Pydantic não propagam entre nós do LangGraph — só o update dict).
        update["team"] = state.team
        update["delegate_to"] = state.delegate_to
        update["supervisor_rounds"] = state.supervisor_rounds
        if state.stop_reason is not None:
            update["stop_reason"] = state.stop_reason
        update.update(self._trace_update(state, entry, started_at))
        return update

    # -----------------------------------------------------------------
    # Helper: tolerant JSON extraction from the LLM content.
    # -----------------------------------------------------------------
    @staticmethod
    def _parse_next_agent(content: str) -> dict | None:
        """Search for a JSON object {@@...@@} at the end of the content."""
        import json
        import re

        # Try to find a JSON object {...} possibly on the last line.
        # Heuristic: look for the last {...} block.
        match = re.search(r"(\{[^}]+\})", content)
        if not match:
            return None
        try:
            obj = json.loads(match.group(1))
            if "next_agent" in obj and (
                isinstance(obj["next_agent"], str) or obj["next_agent"] is None
            ):
                return obj
        except (json.JSONDecodeError, TypeError):
            pass
        return None


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
        # Execução paralela básica (Etapa 1): a chamada ao gateway, a coleta de
        # fontes e o scan ativo são pernas independentes — rodam em concorrência
        # em vez de uma após a outra. Ambas são self-contained (nunca levantam
        # para fora) e só-leitura sobre `state`; `asyncio.gather` preserva a
        # ordem dos resultados, então o state update e a contabilidade de tokens
        # ficam idênticos ao fluxo sequencial anterior.
        async def _safe_scan() -> ScanReport | None:
            if state.scan_service is None:
                return None
            try:
                return await state.scan_service.scan(state.target)
            except ScanBlockedError:
                return None

        if get_settings().agent_parallel:
            result, sources, report = await asyncio.gather(
                self._attempt(state),
                self._collect_sources(state),
                _safe_scan(),
            )
        else:
            result = await self._attempt(state)
            sources = await self._collect_sources(state)
            report = await _safe_scan()
        new_confidence = min(1.0, state.confidence + 0.4)
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

        # Scanning ativo (Etapa 12): quando injetado e o alvo está em escopo
        # validado, o Eremita também observa o alvo diretamente (headers,
        # forms, fingerprint) e gera leads evidence-grounded — independente
        # do Modo Diabo. Um scan bloqueado (kill-switch/fora de escopo) é
        # silencioso: nunca fabrica finding sem dado real observado.
        scan_findings_derived = (
            derive_findings_from_scan(report) if report is not None else []
        )
        for finding in scan_findings_derived:
            if finding["title"] in existing_titles:
                continue
            finding["id"] = f"F-{len(state.findings) + len(findings) + 1}"
            findings.append(finding)

        # Correlação CVE por fingerprint (Etapa 13): o banner versado do servidor
        # (ex.: Apache/2.4.49) é correlacionado a CVEs reais via NVD + CISA KEV,
        # gerando leads candidate com cves/cvss/known_exploits de verdade.
        correlated = await _correlate_cves(state, report) if report is not None else []
        for finding in correlated:
            if finding["title"] in existing_titles:
                continue
            finding["id"] = f"F-{len(state.findings) + len(findings) + 1}"
            findings.append(finding)

        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "simulate",
            "findings": len(findings),
            "sources_consulted": len(sources),
            "scanned": report is not None,
            "pages_observed": len(report.pages) if report is not None else 0,
            "cve_correlations": len(correlated),
        }
        update: dict[str, Any] = {
            "findings": [*state.findings, *findings],
            "confidence": new_confidence,
            "sources": [*state.sources, *sources],
        }
        if report is not None:
            update["scan"] = [*state.scan, report.to_dict()]
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
        # Pernas independentes rodam em concorrência (Etapa 1, paralelo básico).
        if get_settings().agent_parallel:
            result, sources = await asyncio.gather(
                self._attempt(state), self._collect_sources(state)
            )
        else:
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
    """Execution node: safety checks + live non-destructive execution
    (modo normal) ou execução controlada (devil)."""

    key = "chariot"
    name = "O Carro"
    role = "executor"
    model_tier = "cheap"
    output_schema = ChariotOutput
    # O Carro é o arquétipo de execução: em modo normal ele pode invocar
    # qualquer tool NÃO destrutiva registrada pelo operador (TOOLS_MANIFEST) —
    # o gating de `destructive` continua sendo a fronteira real (destrutivo só
    # no Modo Diabo).
    allowed_tools: tuple[str, ...] = ("*",)

    def system_prompt(self) -> str:
        return (
            "You are O Carro, the controlled-execution archetype. "
            "In normal mode you perform non-invasive safety checks over signals "
            "already observed (passive scan, configured sources, CVE "
            "correlation) and MAY re-probe the target live to verify candidate "
            "findings and run operator-provided non-destructive tools — you "
            "never run anything destructive or evasive. "
            "In execution (devil) mode you only act when the run is explicitly "
            "in execution mode AND a human operator has approved this specific "
            "action against the authorized target — never on your own "
            "initiative. Your response is a short factual record of the action "
            "taken and its outcome, for the audit log. "
            "Never describe technique detail, payload content, or step-by-step "
            "instructions of any kind."
        )

    async def run(self, state: GraphState) -> dict:
        from app.core.security import is_devil_mode_enabled

        if not is_devil_mode_enabled(state.devil_mode):
            return await self._safety_check(state)
        return await self._controlled_execution(state)

    async def _safety_check(self, state: GraphState) -> dict:
        """Safety check + execução real NÃO destrutiva (modo normal).

        Observa sinais não invasivos já disponíveis (scan passivo + fontes
        configuradas + correlação CVE por banner) e marca indícios de risco
        como achados candidatos (`requires_human_review=True`). Em seguida,
        com `mode="live"`, executa a camada real (Etapa 15): re-prova os
        candidatos contra o alvo ao vivo (verificação) e invoca as tools NÃO
        destrutivas do operador. Nada destrutivo roda; um scan/probe bloqueado
        (kill-switch/fora de escopo) é silencioso — nunca fabrica achado sem
        dado real observado.
        """
        started_at = _utcnow()

        async def _safe_scan() -> ScanReport | None:
            if state.scan_service is None:
                return None
            try:
                return await state.scan_service.scan(state.target)
            except ScanBlockedError:
                return None

        if get_settings().agent_parallel:
            result, sources, report = await asyncio.gather(
                self._attempt(state),
                self._collect_sources(state),
                _safe_scan(),
            )
        else:
            result = await self._attempt(state)
            sources = await self._collect_sources(state)
            report = await _safe_scan()

        existing_titles = {f.get("title") for f in state.findings}
        derived_sources = derive_findings_from_sources(
            state.target.get("name", "unknown"), sources
        )
        derived_scan = derive_findings_from_scan(report) if report is not None else []
        correlated = await _correlate_cves(state, report) if report is not None else []
        findings: list[dict[str, Any]] = []
        for finding in [*derived_sources, *derived_scan, *correlated]:
            if finding["title"] in existing_titles:
                continue
            finding["id"] = f"F-{len(state.findings) + len(findings) + 1}"
            findings.append(finding)

        # Execução real não destrutiva: verificação ao vivo + tools do operador.
        tool_runs, verified, refuted = await self._live_execution(state, findings, report)

        new_confidence = min(1.0, state.confidence + 0.2)
        live = bool(verified or refuted or tool_runs)
        entry: dict[str, Any] = {
            "agent": self.key,
            "action": "safety",
            "mode": "live" if live else "simulate",
            "findings": len(findings),
            "sources_consulted": len(sources),
            "scanned": report is not None,
            "pages_observed": len(report.pages) if report is not None else 0,
            "cve_correlations": len(correlated),
        }
        if live:
            entry["verified"] = verified
            entry["refuted"] = refuted
            entry["tools_tried"] = len(tool_runs)
        if tool_runs:
            entry["tool_runs"] = tool_runs
        update: dict[str, Any] = {
            "findings": [*state.findings, *findings],
            "confidence": new_confidence,
            "sources": [*state.sources, *sources],
        }
        if report is not None:
            update["scan"] = [*state.scan, report.to_dict()]
        _apply_llm(entry, update, state, result, fallback_tokens=200)
        entry = self.validate_entry(entry)
        update["history"] = [*state.history, entry]
        update.update(
            self._trace_update(state, entry, started_at, confidence_after=new_confidence)
        )
        return update

    async def _live_execution(
        self,
        state: GraphState,
        findings: list[dict[str, Any]],
        report: ScanReport | None,
    ) -> tuple[list[dict[str, Any]], int, int]:
        """Layer de execução real NÃO destrutiva de um run normal (Etapa 15).

        1. **Verificação ao vivo:** re-prova os achados vindos do scan contra
           o alvo (sondas GET no escopo/robots/rate-limit) e anexa
           ``finding["verification"]`` (confirmado ou refutado com evidência
           presencial).
        2. **Tools do operador:** invoca uma vez cada tool NÃO destrutiva do
           `TOOLS_MANIFEST` (gating `destructive` da Etapa 5 respeitado).

        Determinístico offline: sem verifier/executor injetados nada roda e as
        contagens ficam zero. Qualquer falha degrada para registro, nunca
        derruba o run.
        """
        verified, refuted = 0, 0
        verifier = state.verification_service
        if verifier is not None:
            try:
                outcomes = await verifier.verify(
                    report=report, findings=findings, target=state.target
                )
            except Exception:  # noqa: BLE001 - execução nunca derruba o run
                outcomes = [None] * len(findings)
            for finding, outcome in zip(findings, outcomes, strict=True):
                if outcome is None:
                    continue
                finding["verification"] = outcome
                if outcome.get("confirmed"):
                    verified += 1
                elif not (outcome.get("probe") or {}).get("skipped"):
                    refuted += 1

        tool_runs: list[dict[str, Any]] = []
        executor = state.tool_executor
        if executor is not None:
            target_name = str(state.target.get("name", ""))
            for spec in executor.registry.specs():
                if spec.destructive:
                    continue
                tool_runs.append(await self._run_tool(executor, spec, target_name))
        return tool_runs, verified, refuted

    async def _run_tool(self, executor: ToolExecutor, tool, target: str) -> dict[str, Any]:
        """Invoke one non-destructive tool once, recording the auditable outcome.

        A falha da tool é registrada (``outcome="failed"``) — jamais torna o
        run inválido; o saída é compactada para caber no histórico.
        """
        started_at = _utcnow()
        try:
            result = await executor.execute(
                tool.name,
                {"target": target, "url": target},
                devil_mode=False,
            )
            return {
                "tool": tool.name,
                "kind": tool.kind.value if isinstance(tool.kind, ToolKind) else str(tool.kind),
                "destructive": False,
                "outcome": "ok",
                "duration_ms": round((_utcnow() - started_at).total_seconds() * 1000, 2),
                "detail": self._compact_tool_result(result),
            }
        except Exception as exc:  # noqa: BLE001 - falha de tool degrada, nunca quebra o run
            return {
                "tool": tool.name,
                "kind": tool.kind.value if isinstance(tool.kind, ToolKind) else str(tool.kind),
                "destructive": False,
                "outcome": "failed",
                "duration_ms": round((_utcnow() - started_at).total_seconds() * 1000, 2),
                "detail": {"note": str(exc)[:300]},
            }

    @staticmethod
    def _compact_tool_result(result: dict[str, Any]) -> dict[str, Any]:
        if "status_code" in result:
            return {
                "status_code": result.get("status_code"),
                "body": str(result.get("body", ""))[:400],
            }
        return {
            "returncode": result.get("returncode"),
            "stdout": str(result.get("stdout", ""))[:400],
            "stderr": str(result.get("stderr", ""))[:300],
        }

    async def _controlled_execution(self, state: GraphState) -> dict:
        """Execução controlada (devil mode): ação destrutiva exige aprovação
        humana por ação e, mesmo aprovada, não há backend de execução real
        plugado nesta instância — registra honestamente que nada rodou."""
        started_at = _utcnow()
        target = state.target.get("name", "unknown")

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
        # orçamento do run ou per-agente); não herda "pending_review" de uma
        # parada HITL anterior — o nó final sempre encerra como "completed".
        if state.stop_reason in ("budget", "agent_budget", "confidence", "declined", "no_backend"):
            final_reason = state.stop_reason
        elif state.tokens_used >= state.budget_tokens or state.cost >= state.budget_cost:
            # Segurança do audit trail para o caso de o orçamento estourar e a
            # marcação não chegar até aqui (ex.: router desviou para a Justiça
            # sem `stop_reason` persistido) — a parada é reportada como budget.
            final_reason = "budget"
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
