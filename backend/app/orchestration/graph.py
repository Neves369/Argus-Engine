from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.graph import END, StateGraph

from app.agents import get_archetype
from app.core.config import get_settings
from app.core.security import is_kill_switch_active
from app.llm.compress import compress_history, llm_summarize_middle
from app.orchestration.hitl import is_answered, resolve
from app.orchestration.state import GraphState


def _is_awaiting_review(state: GraphState) -> bool:
    return state.pending_review is not None and not is_answered(state)


def _noop_provision(state: GraphState) -> None:
    return None


def _budgeted_out(state: GraphState) -> str | None:
    """Orçamento run-wide esgotado: retorna ``"budget"`` (e marca o
    ``stop_reason`` do estado local); senão ``None``."""
    if state.tokens_used >= state.budget_tokens or state.cost >= state.budget_cost:
        if state.stop_reason is None:
            state.stop_reason = "budget"
        return "budget"
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
            if settings.history_llm_summary and not state.history_summary_done:
                state.history, _ = await llm_summarize_middle(
                    state.history,
                    keep_first=1,
                    keep_last=settings.history_keep_last,
                )
                state.history_summary_done = True
            else:
                state.history = compress_history(
                    state.history,
                    keep_first=1,
                    keep_last=settings.history_keep_last,
                )
        result = await fn(state)
        # Orçamento do run esgotado: marca ``stop_reason="budget"`` no update
        # do nó (só o dict de retorno persiste no grafo — mutar o estado
        # dentro de um router condicional se perde). Não sobrescreve paradas
        # mais específicas do nó nem interfere num HITL pendente.
        if isinstance(result, dict):
            if state.history_summary_done and result.get("history_summary_done") is None:
                result["history_summary_done"] = True
            if not _is_awaiting_review(state):
                if result.get("stop_reason") is None and _budgeted_out(state) is not None:
                    result["stop_reason"] = "budget"
        return result

    return node


async def _emperor(state: GraphState) -> dict:
    return await get_archetype("emperor").run(state)


async def _human_gate(state: GraphState) -> dict:
    """Consume an answered human decision; no-op while still awaiting."""
    if not state.pending_review or _is_awaiting_review(state):
        return {}
    return resolve(state)


def route_from_emperor(state: GraphState) -> str:
    """Roteador do Imperador: decide o próximo nó após a fase de plan."""
    if _is_awaiting_review(state):
        return "gate"
    if state.delegate_to and state.delegate_to in state.team:
        return state.delegate_to
    # Se não houver delegação válida, encerra para a Justiça.
    return "justice"


def route_after_worker(state: GraphState) -> str:
    """Roteador pós-agente de um worker no grafo supervisionado.

    Quem decide o fechamento por confiança é o Imperador (supervisor), não o
    worker: o worker coleta e sempre devolve o controle; o Imperador fecha
    quando o time já produziu confiança suficiente ou esgotou as rodadas.
    Paradas inadiáveis (HITL pendente, kill-switch, orçamento do run ou um
    `stop_reason` definitivo definido pelo worker ou pelo gate após a decisão
    humana) desviam direto para a Justiça validar e fechar.

    Returns:
        "emperor" — volta para o Imperador decidir o próximo agente.
        "justice" — encerra o run (orçamento, kill-switch ou stop_reason).
        "gate" — pausa para decisão humana (HITL).
    """
    if _is_awaiting_review(state):
        return "gate"
    if is_kill_switch_active():
        return "justice"
    if state.stop_reason is not None:
        return "justice"
    if _budgeted_out(state) is not None:
        return "justice"
    return "emperor"


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


def _build_supervised(entry: str | None, provision: Callable[[GraphState], None]) -> StateGraph:
    graph = StateGraph(GraphState)

    # Add all possible archetype nodes (the routing logic checks team membership).
    for key in ("emperor", "fool", "hermit", "magician", "chariot", "justice"):
        if key == "emperor":
            graph.add_node(key, _provisioned(_emperor, provision))
        else:
            graph.add_node(key, _make_node(key, provision))
    graph.add_node("human_gate", _provisioned(_human_gate, provision))

    # Entry point.
    entry_point = entry or "emperor"
    graph.set_entry_point(entry_point)

    # --- Emperor conditional edges ---
    emperor_edges: dict[str, str] = {
        "fool": "fool",
        "hermit": "hermit",
        "magician": "magician",
        "chariot": "chariot",
        "justice": "justice",
        "gate": "human_gate",
    }
    graph.add_conditional_edges(
        "emperor",
        route_from_emperor,
        emperor_edges,
    )

    # --- Worker conditional edges ---
    worker_edges: dict[str, str] = {
        "emperor": "emperor",
        "justice": "justice",
        "gate": "human_gate",
    }
    for worker in ("fool", "hermit", "magician", "chariot"):
        graph.add_conditional_edges(
            worker,
            route_after_worker,
            worker_edges,
        )

    # --- Human gate edges (preserve existing behaviour) ---
    known = frozenset({"fool", "hermit", "magician", "chariot", "justice"})
    gate_map = {
        "fool": "fool",
        "hermit": "hermit",
        "magician": "magician",
        "chariot": "chariot",
        "justice": "justice",
        "end": END,
    }
    graph.add_conditional_edges(
        "human_gate",
        lambda s: _collect_edges(s, known),
        gate_map,
    )

    graph.add_edge("justice", END)

    return graph


def build_graph(
    archetypes: list[str] | None = None,
    *,
    entry: str | None = None,
    provision: Callable[[GraphState], None] | None = None,
) -> StateGraph:
    provision = provision or _noop_provision
    # Supervisor universal: o Imperador rege todo run (com ou sem cartas).
    # O `team` (quem ele pode escalar) é resolvido em runtime na provision do
    # Director — completo quando `archetypes` está vazio, restrito às cartas
    # escolhidas quando há composição. A ordem das cartas não importa: o grafo
    # supervisionado deixa o Imperador decidir e repetir agentes conforme
    # necessário. O pipeline linear (carta uma única vez na ordem) foi
    # substituído por esse modelo.
    return _build_supervised(entry, provision)


def compile_graph(
    archetypes: list[str] | None = None,
    *,
    entry: str | None = None,
    provision: Callable[[GraphState], None] | None = None,
):
    return build_graph(archetypes, entry=entry, provision=provision).compile()
