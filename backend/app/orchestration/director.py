from __future__ import annotations

from app.orchestration.graph import compile_graph
from app.orchestration.state import GraphState


class Director:
    """Top-level orchestrator exposing the minimal run/pause/resume interface."""

    def __init__(self) -> None:
        self._graph = compile_graph()
        self._paused = False

    async def run(self, state: GraphState) -> GraphState:
        result = await self._graph.ainvoke(state.model_dump())
        if isinstance(result, GraphState):
            return result
        return GraphState.model_validate(result)

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    async def inject_human_input(self, message: str) -> None:
        """Placeholder for human-in-the-loop (Etapa 10)."""
        raise NotImplementedError("Human-in-the-loop is not implemented yet.")
