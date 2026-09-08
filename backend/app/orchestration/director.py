from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from app.orchestration.graph import compile_graph
from app.orchestration.state import GraphState


class Director:
    """Top-level orchestrator exposing the run/pause/resume interface.

    ``sources_service`` (and any runtime dependency) is injected into the graph
    via a ``provision`` hook, since langgraph rebuilds the state object between
    nodes and drops non-serialized attributes.
    """

    def __init__(
        self,
        archetypes: list[str] | None = None,
        *,
        sources_service: Any = None,
        scan_service: Any = None,
    ) -> None:
        self._archetypes = archetypes
        self._sources_service = sources_service
        self._scan_service = scan_service

        def provision(state: GraphState) -> None:
            if sources_service is not None:
                state.set_sources_service(sources_service)
            if scan_service is not None:
                state.set_scan_service(scan_service)
            # O time do supervisor (quem o Imperador pode delegar) é resolvido
            # na primeira passada. Nunca sobrescreve um team já persistido
            # (resume de run HITL mantém o time original). O estado persistido
            # (composition) tem precedência; `self._archetypes` cobre chamadas
            # diretas ao Director sem composition no estado.
            if not state.team:
                state.team = self._resolve_team(state, self._archetypes)

        self._provision = provision

    @classmethod
    def _resolve_team(cls, state: GraphState, archetypes: list[str] | None = None) -> list[str]:
        """Time do supervisor (que o Imperador pode escalar).

        O Imperador rege todo run: sem cartas ele tem o time completo
        disponível; com composição ele escala apenas as cartas escolhidas
        (menos a Justiça, que é sempre o fechador fixo). A ordem das cartas
        não importa — vira só o conjunto liberado. Sensível ao `devil_mode`:
        num run de execução o Carro entra no time (e para no HITL exigido);
        caso contrário o Carro fica de fora e não é delegado.
        """
        base = state.composition or archetypes or []
        if base:
            # A Justiça é sempre o fechador fixo (não é "delegável"); o
            # Imperador não é carta sob o modelo universal (rege todo run).
            team = [a for a in base if a not in ("justice", "emperor")]
        else:
            team = ["fool", "hermit", "magician"]
        if state.devil_mode and "chariot" not in team:
            team.append("chariot")
        return team

    def _compile(self, entry: str | None = None):
        return compile_graph(self._archetypes, entry=entry, provision=self._provision)

    async def run(self, state: GraphState) -> GraphState:
        """Execute the graph; a run halts (not completed) when it awaits review."""
        result = await self._compile().ainvoke(state.model_dump())
        if isinstance(result, GraphState):
            return result
        return GraphState.model_validate(result)

    async def run_from(self, state: GraphState, entry: str) -> GraphState:
        """Resume a run starting at ``entry`` with a human decision applied."""
        result = await self._compile(entry).ainvoke(state.model_dump())
        if isinstance(result, GraphState):
            return result
        return GraphState.model_validate(result)

    async def stream(
        self, state: GraphState, *, entry: str | None = None
    ) -> AsyncGenerator[dict, None]:
        """Yield per-node updates as the graph executes.

        ``entry`` retoma a partir de um nó específico (padrão: o Imperador).
        """
        async for event in self._compile(entry).astream(
            state.model_dump(), stream_mode="updates"
        ):
            yield event

    def resume_agent(self, state: GraphState) -> str:
        """Nó por onde um run interrompido (cancelado/falho) volta a rodar.

        Usa o ``next_agent`` reservado pelo estado; sem ele, a primeira carta
        da composição (time restrito) ou o Imperador (supervisor universal).
        """
        entry = state.next_agent
        if not entry:
            entry = (
                state.composition[0]
                if state.composition
                else (self._archetypes[0] if self._archetypes else "emperor")
            )
        return entry

    async def resume(self, state: GraphState) -> GraphState:
        """Resume from the state's ``next_agent`` (used after /review)."""
        return await self.run_from(state, self.resume_agent(state))

    async def inject_human_input(self, state: GraphState, decision: dict[str, Any]) -> GraphState:
        """Apply a human decision to a pending review and resume the run."""
        state.human_decision = decision
        return await self.resume(state)
