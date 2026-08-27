from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import get_archetype
from app.core.config import get_settings
from app.core.security import is_devil_mode_enabled, is_kill_switch_active
from app.orchestration.state import GraphState


async def emperor_node(state: GraphState) -> dict:
    return await get_archetype("emperor").run(state)


async def hermit_node(state: GraphState) -> dict:
    return await get_archetype("hermit").run(state)


async def chariot_node(state: GraphState) -> dict:
    return await get_archetype("chariot").run(state)


async def justice_node(state: GraphState) -> dict:
    return await get_archetype("justice").run(state)


def route_after_director(state: GraphState) -> str:
    if is_devil_mode_enabled(state.devil_mode):
        return "chariot"
    return "hermit"


def should_continue(state: GraphState) -> str:
    settings = get_settings()

    if is_kill_switch_active():
        return "stop"

    if state.tokens_used >= state.budget_tokens or state.cost >= state.budget_cost:
        return "stop"

    if state.confidence >= settings.confidence_threshold:
        return "stop"

    return route_after_director(state)


def _make_node(key: str) -> Callable[[GraphState], Any]:
    async def node(state: GraphState) -> dict:
        return await get_archetype(key).run(state)

    return node


def _build_default() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("emperor", emperor_node)
    graph.add_node("hermit", hermit_node)
    graph.add_node("chariot", chariot_node)
    graph.add_node("justice", justice_node)

    graph.set_entry_point("emperor")
    graph.add_conditional_edges(
        "emperor",
        route_after_director,
        {"hermit": "hermit", "chariot": "chariot"},
    )
    graph.add_conditional_edges(
        "hermit",
        should_continue,
        {"hermit": "hermit", "chariot": "chariot", "stop": "justice"},
    )
    graph.add_conditional_edges(
        "chariot",
        should_continue,
        {"hermit": "hermit", "chariot": "chariot", "stop": "justice"},
    )
    graph.add_edge("justice", END)

    return graph


def _build_pipeline(archetypes: list[str]) -> StateGraph:
    graph = StateGraph(GraphState)

    for key in archetypes:
        graph.add_node(key, _make_node(key))

    graph.set_entry_point(archetypes[0])
    for current, following in zip(archetypes, archetypes[1:], strict=False):
        graph.add_edge(current, following)
    graph.add_edge(archetypes[-1], END)

    return graph


def build_graph(archetypes: list[str] | None = None) -> StateGraph:
    if archetypes is None:
        return _build_default()
    return _build_pipeline(archetypes)


def compile_graph(archetypes: list[str] | None = None):
    return build_graph(archetypes).compile()
