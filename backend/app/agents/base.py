from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.llm.router import attempt_completion
from app.orchestration.state import GraphState


class BaseArchetype(ABC):
    """Contract shared by all agent archetypes.

    Each concrete archetype declares its role, preferred model tier and allowed tools,
    and implements `run()` which returns a partial GraphState update.
    """

    key: str = "base"
    name: str = "Base"
    role: str = "generic"
    model_tier: str = "cheap"
    allowed_tools: tuple[str, ...] = ()

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}, the {self.role} archetype. "
            "Operate only within the authorized scope. Be concise. "
            "Return only a short, factual assessment — no techniques, no payloads."
        )

    def _context(self, state: GraphState) -> str:
        name = state.target.get("name", "unknown")
        return (
            f"Target: {name}\n"
            f"Findings: {len(state.findings)}\n"
            f"Evidence: {len(state.evidence)}\n"
            f"Sources consulted: {len(state.sources)}\n"
            f"Confidence: {state.confidence:.2f}\n"
            f"Tokens used so far: {state.tokens_used}\n"
            f"Mode: {'execute' if state.devil_mode else 'simulate'}"
        )

    async def _collect_sources(self, state: GraphState) -> list[dict]:
        """Query every configured data source by role, without knowing specific
        sources. Returns normalized/fallback results (deterministic offline).
        """
        service = state.sources_service
        if service is None:
            return []

        from app.sources.service import DataSourceError

        query = {"q": state.target.get("name", "")}
        results: list[dict] = []
        for name in service.available_sources():
            try:
                results.append(await service.query(name, query))
            except DataSourceError:
                continue
        return results

    async def _attempt(self, state: GraphState, *, devil_mode: bool = False):
        """Try the LLM gateway; return ``None`` when the call is unavailable."""
        return await attempt_completion(
            self.system_prompt(), self._context(state), devil_mode=devil_mode
        )

    def _request_approval(
        self,
        state: GraphState,
        *,
        kind: str,
        context: str,
        proposal: dict[str, Any] | None = None,
        next_node: str | None = None,
    ) -> dict[str, Any]:
        """Declare a human-in-the-loop decision point for this agent.

        Returns the partial state update that pauses the run until ``/review``
        answers it. The graph routes to ``human_gate`` (or back into this node on
        resume) so the gated action only runs after operator approval.
        """
        from app.orchestration.hitl import request_approval

        return request_approval(
            state,
            kind=kind,
            context=context,
            proposal=proposal,
            next_node=next_node,
        )

    @abstractmethod
    async def run(self, state: GraphState) -> dict:
        """Execute the archetype's task and return a partial state update."""
        raise NotImplementedError
