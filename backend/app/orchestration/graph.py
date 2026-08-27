from __future__ import annotations

from langgraph.graph import END, StateGraph

from app.agents import get_archetype
from app.core.config import get_settings
from app.core.security import is_kill_switch_active
from app.orchestration.state import GraphState


async def director_node(state: GraphState) -> dict:
    return await get_archetype("director").run(state)


async def collector_node(state: GraphState) -> dict:
    return await get_archetype("collector").run(state)


async def analyst_node(state: GraphState) -> dict:
    return await get_archetype("analyst").run(state)


def should_continue(state: GraphState) -> str:
    settings = get_settings()

    if is_kill_switch_active():
        return "stop"

    if state.tokens_used >= state.budget_tokens or state.cost >= state.budget_cost:
        return "stop"

    if state.confidence >= settings.confidence_threshold:
        return "stop"

    return "collector"


def build_graph() -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("director", director_node)
    graph.add_node("collector", collector_node)
    graph.add_node("analyst", analyst_node)

    graph.set_entry_point("director")
    graph.add_edge("director", "collector")
    graph.add_conditional_edges(
        "collector",
        should_continue,
        {"collector": "collector", "stop": "analyst"},
    )
    graph.add_edge("analyst", END)

    return graph


def compile_graph():
    return build_graph().compile()
