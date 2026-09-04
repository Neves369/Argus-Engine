from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import get_archetype
from app.core.config import get_settings
from app.core.security import is_devil_mode_enabled, is_kill_switch_active
from app.llm.compress import compress_history
from app.orchestration.hitl import is_answered, resolve
from app.orchestration.state import GraphState


def _is_awaiting_review(state: GraphState) -> bool:
    return state.pending_review is not None and not is_answered(state)


def _noop_provision(state: GraphState) -> None:
    return None


def _provisioned(
    fn: Callable[[GraphState], Any], provision: Callable[[GraphState], None]
) -> Callable[[GraphState], Any]:
    async def node(state: GraphState) -> dict:
        if provision is not None:
            provision(state)
        settings = get_settings()
        if (
            settings.history_compression
            and len(state.history) > settings.history_keep_last + 1
        ):
            state.history = compress_history(
                state.history,
                keep_first=1,
                keep_last=settings.history_keep_last,
            )
        result = await fn(state)
        return result

    return node


async def _emperor(state: GraphState) -> dict:
    return await get_archetype("emperor").run(state)


async def _hermit(state: GraphState) -> dict:
    return await get_archetype("hermit").run(state)


async def _chariot(state: GraphState) -> dict:
    return await get_archetype("chariot").run(state)


async def _justice(state: GraphState) -> dict:
    return await get_archetype("justice").run(state)


async def _human_gate(state: GraphState) -> dict:
    """Consume an answered human decision; no-op while still awaiting."""
    if not state.pending_review or _is_awaiting_review(state):
        return {}
    return resolve(state)


def route_after_director(state: GraphState) -> str:
    if _is_awaiting_review(state):
        return "gate"
    if is_devil_mode_enabled(state.devil_mode):
        return "chariot"
    return "hermit"


def should_continue(state: GraphState) -> str:
    settings = get_settings()

    if _is_awaiting_review(state):
        return "gate"
    if is_kill_switch_active():
        return "stop"
    # A node that already set a definitive stop_reason (e.g. Chariot's
    # "declined"/"no_backend" outcomes) must end the run immediately —
    # without this, the graph fell through to route_after_director() and
    # looped back into the same node repeatedly (re-declining, re-reporting
    # no backend) until the token/cost budget ran out, burning real LLM
    # spend on a foregone conclusion.
    if state.stop_reason is not None:
        return "stop"
    if state.tokens_used >= state.budget_tokens or state.cost >= state.budget_cost:
        if state.stop_reason is None:
            state.stop_reason = "budget"
        return "stop"
    # Per-agent budget: only checked against the archetype about to run NEXT
    # (route_after_director's choice) — an agent already over its own cap
    # must not be allowed to loop again, even if the run-wide budget still
    # has headroom. Off by default (both settings 0).
    next_node = route_after_director(state)
    if next_node in ("hermit", "chariot"):
        over_tokens = (
            settings.budget_tokens_per_agent > 0
            and state.tokens_by_agent.get(next_node, 0) >= settings.budget_tokens_per_agent
        )
        over_cost = (
            settings.budget_cost_per_agent > 0
            and state.cost_by_agent.get(next_node, 0.0) >= settings.budget_cost_per_agent
        )
        if over_tokens or over_cost:
            if state.stop_reason is None:
                state.stop_reason = "agent_budget"
            return "stop"
    if state.confidence >= settings.confidence_threshold:
        if state.stop_reason is None:
            state.stop_reason = "confidence"
        return "stop"

    return next_node


def after_gate(state: GraphState, known: frozenset[str] = frozenset()) -> str:
    if _is_awaiting_review(state):
        return "end"
    if state.human_gate_next and state.human_gate_next in known:
        return state.human_gate_next
    return "end"


def _make_node(
    key: str, provision: Callable[[GraphState], None]
) -> Callable[[GraphState], Any]:
    return _provisioned(lambda state: get_archetype(key).run(state), provision)


def _collect_edges(state: GraphState, known: frozenset[str]) -> str:
    return after_gate(state, known)


def _build_default(
    entry: str | None, provision: Callable[[GraphState], None]
) -> StateGraph:
    graph = StateGraph(GraphState)

    graph.add_node("emperor", _provisioned(_emperor, provision))
    graph.add_node("hermit", _provisioned(_hermit, provision))
    graph.add_node("chariot", _provisioned(_chariot, provision))
    graph.add_node("justice", _provisioned(_justice, provision))
    graph.add_node("human_gate", _provisioned(_human_gate, provision))

    graph.set_entry_point(entry or "emperor")

    default_edges: dict[str, str] = {
        "hermit": "hermit",
        "chariot": "chariot",
        "gate": "human_gate",
        "stop": "justice",
    }
    graph.add_conditional_edges(
        "emperor",
        route_after_director,
        {"hermit": "hermit", "chariot": "chariot", "gate": "human_gate"},
    )
    graph.add_conditional_edges("hermit", should_continue, default_edges)
    graph.add_conditional_edges("chariot", should_continue, default_edges)

    gate_map = {
        "hermit": "hermit",
        "chariot": "chariot",
        "justice": "justice",
        "end": END,
    }
    graph.add_conditional_edges(
        "human_gate",
        lambda s: _collect_edges(s, frozenset({"hermit", "chariot", "justice"})),
        gate_map,
    )
    graph.add_edge("justice", END)

    return graph


def _build_pipeline(
    archetypes: list[str], entry: str | None, provision: Callable[[GraphState], None]
) -> StateGraph:
    graph = StateGraph(GraphState)

    for key in archetypes:
        graph.add_node(key, _make_node(key, provision))
    graph.add_node("human_gate", _provisioned(_human_gate, provision))

    graph.set_entry_point(entry or archetypes[0])

    for i, current in enumerate(archetypes):
        following = archetypes[i + 1] if i + 1 < len(archetypes) else None

        def _route(state: GraphState) -> str:
            if _is_awaiting_review(state):
                return "gate"
            return "next"

        edge_map: dict[str, Any] = {"gate": "human_gate"}
        edge_map["next"] = following if following is not None else END
        graph.add_conditional_edges(current, _route, edge_map)

    gate_map: dict[str, Any] = {n: n for n in archetypes}
    gate_map["end"] = END
    known = frozenset(archetypes)
    graph.add_conditional_edges(
        "human_gate", lambda s: _collect_edges(s, known), gate_map
    )

    return graph


def build_graph(
    archetypes: list[str] | None = None,
    *,
    entry: str | None = None,
    provision: Callable[[GraphState], None] | None = None,
) -> StateGraph:
    provision = provision or _noop_provision
    if archetypes is None:
        return _build_default(entry, provision)
    return _build_pipeline(archetypes, entry, provision)


def compile_graph(
    archetypes: list[str] | None = None,
    *,
    entry: str | None = None,
    provision: Callable[[GraphState], None] | None = None,
):
    return build_graph(archetypes, entry=entry, provision=provision).compile()
