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
    ) -> None:
        self._archetypes = archetypes
        self._sources_service = sources_service

        def provision(state: GraphState) -> None:
            if sources_service is not None:
                state.set_sources_service(sources_service)

        self._provision = provision

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

    async def stream(self, state: GraphState) -> AsyncGenerator[dict, None]:
        """Yield per-node updates as the graph executes."""
        async for event in self._compile().astream(state.model_dump(), stream_mode="updates"):
            yield event

    async def resume(self, state: GraphState) -> GraphState:
        """Resume from the state's ``next_agent`` (used after /review)."""
        entry = state.next_agent
        if not entry:
            entry = (self._archetypes[0] if self._archetypes else "emperor")
        return await self.run_from(state, entry)

    async def inject_human_input(self, state: GraphState, decision: dict[str, Any]) -> GraphState:
        """Apply a human decision to a pending review and resume the run."""
        state.human_decision = decision
        return await self.resume(state)
