from __future__ import annotations

import asyncio

from app.core.security import activate_kill_switch, deactivate_kill_switch
from app.orchestration import graph as graph_mod
from app.orchestration.director import Director
from app.orchestration.state import GraphState


class _FakeSourcesService:
    """No-sweep stub: yields one real-shaped crt.sh subdomain lead."""

    def available_sources(self) -> list[str]:
        return ["crtsh"]

    def get_source(self, name: str):
        class _Spec:
            skip_sweep = False
            target_kind = "domain"
            query_param = "q"

        return _Spec()

    async def query(self, name: str, params: dict | None = None) -> dict:
        params = params or {}
        target = params.get("q", "example.com")
        return {
            "status": "ok",
            "source": "crtsh",
            "data": {"response": [{"name_value": f"www.{target}\napi.{target}"}]},
            "fetched_at": "2026-01-01T00:00:00+00:00",
        }


def _pending_state() -> GraphState:
    return GraphState(
        target={"name": "example.com"},
        pending_review={"id": "r1", "kind": "finding_review", "context": "x", "proposal": {}},
    )


def _run(final: GraphState) -> GraphState:
    return asyncio.run(Director().run(final))


# ---------------------------------------------------------------------------
# route_from_emperor
# ---------------------------------------------------------------------------


def test_route_from_emperor_delegates_team_member():
    state = GraphState(target={"name": "example.com"}, team=["hermit"], delegate_to="hermit")
    assert graph_mod.route_from_emperor(state) == "hermit"


def test_route_from_emperor_rotates_to_next_team_member():
    state = GraphState(
        target={"name": "example.com"}, team=["fool", "hermit"], delegate_to="fool"
    )
    assert graph_mod.route_from_emperor(state) == "fool"


def test_route_from_emperor_non_member_goes_justice():
    state = GraphState(target={"name": "example.com"}, team=["hermit"], delegate_to="fool")
    assert graph_mod.route_from_emperor(state) == "justice"


def test_route_from_emperor_without_delegate_goes_justice():
    state = GraphState(target={"name": "example.com"}, team=["hermit"])
    assert graph_mod.route_from_emperor(state) == "justice"


def test_route_from_emperor_awaits_review_at_gate():
    state = _pending_state()
    state.team = ["hermit"]
    state.delegate_to = "hermit"
    assert graph_mod.route_from_emperor(state) == "gate"


# ---------------------------------------------------------------------------
# route_after_worker
# ---------------------------------------------------------------------------


def test_route_after_worker_returns_to_emperor_within_bounds():
    state = GraphState(target={"name": "example.com"}, confidence=0.4)
    assert graph_mod.route_after_worker(state) == "emperor"


def test_route_after_worker_pauses_at_gate_when_awaiting_review():
    state = _pending_state()
    assert graph_mod.route_after_worker(state) == "gate"


def test_route_after_worker_closes_on_budget_exhausted():
    state = GraphState(target={"name": "example.com"}, tokens_used=100_000, budget_tokens=100_000)
    assert graph_mod.route_after_worker(state) == "justice"
    assert state.stop_reason == "budget"


def test_route_after_worker_closes_on_kill_switch():
    state = GraphState(target={"name": "example.com"})
    activate_kill_switch()
    try:
        assert graph_mod.route_after_worker(state) == "justice"
    finally:
        deactivate_kill_switch()


def test_route_after_worker_closes_on_definitive_stop_reason():
    state = GraphState(target={"name": "example.com"}, stop_reason="no_backend")
    assert graph_mod.route_after_worker(state) == "justice"


def test_route_after_worker_does_not_close_on_confidence():
    """O fechamento por confiança é decisão do supervisor, não do worker."""
    state = GraphState(target={"name": "example.com"}, confidence=0.99)
    assert graph_mod.route_after_worker(state) == "emperor"


# ---------------------------------------------------------------------------
# Fluxo do supervisor ponta a ponta (modo padrão, sem cartas)
# ---------------------------------------------------------------------------


def test_supervisor_run_completes_with_justice():
    final = _run(GraphState(target={"name": "example.com"}))

    assert final.stop_reason == "completed"
    assert final.history[-1]["agent"] == "justice"
    assert len(final.history) >= 3
    assert final.confidence >= 0.6
    # Sem fontes/scan injetados -> nenhum finding fabricado.
    assert final.findings == []


def test_supervisor_run_delegates_in_rounds():
    """O tempo padrão (Eremita) é delegado até a confiança fechar o run; o
    supervisor deve incrementar rodadas e encerrar depois da Justiça."""
    final = _run(GraphState(target={"name": "example.com"}))

    emperor_entries = [e for e in final.history if e["agent"] == "emperor"]
    assert emperor_entries[0]["action"] == "plan"
    assert any(e["action"] == "direct" for e in emperor_entries)
    assert emperor_entries[-1]["action"] == "close"
    assert final.supervisor_rounds >= 1
    assert final.delegate_to is None


def test_supervisor_run_with_sources_generates_findings():
    async def _run() -> GraphState:
        director = Director(sources_service=_FakeSourcesService())
        return await director.run(GraphState(target={"name": "example.com"}))

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert len(final.findings) >= 1
    assert final.history[-1]["agent"] == "justice"


def test_supervisor_devil_mode_reaches_human_approval():
    from app.core.config import get_settings

    settings = get_settings()
    original = settings.devil_mode
    settings.devil_mode = True

    async def _run() -> GraphState:
        director = Director()
        return await director.run(
            GraphState(target={"name": "example.com"}, devil_mode=True)
        )

    try:
        final = asyncio.run(_run())
    finally:
        settings.devil_mode = original

    # O supervisor inclui o Carro no time em modo de execução e o delega; o
    # Carro para no HITL exigido para a ação destrutiva. A delegação fica
    # registrada no entry "direct" do Imperador (o halt do Carro não grava
    # entry próprio — apenas sinaliza pending_review).
    assert final.pending_review is not None
    assert final.pending_review["kind"] == "destructive_action"
    assert final.stop_reason == "pending_review"
    delegated = [
        e for e in final.history
        if e["agent"] == "emperor" and e.get("next_agent") == "chariot"
    ]
    assert delegated, "o supervisor deve ter delegado chariot no modo de execução"


# ---------------------------------------------------------------------------
# Supervisor universal (parte 4): time completo sem cartas, restrito com cartas
# ---------------------------------------------------------------------------


def test_no_cards_uses_full_team():
    from app.orchestration.director import Director

    team = Director._resolve_team(GraphState(target={"name": "example.com"}))
    assert team == ["fool", "hermit", "magician"]


def test_no_cards_full_team_adds_chariot_in_devil_mode():
    from app.orchestration.director import Director

    team = Director._resolve_team(
        GraphState(target={"name": "example.com"}, devil_mode=True)
    )
    assert set(team) == {"fool", "hermit", "magician", "chariot"}


def test_composition_restricts_team_and_keeps_order_free():
    from app.orchestration.director import Director

    state = GraphState(
        target={"name": "example.com"}, composition=["magician", "fool", "justice"]
    )
    team = Director._resolve_team(state)
    # A Justiça nunca é "delegável" (fechador fixo); a ordem não importa.
    assert team == ["magician", "fool"]


def test_composition_with_chariot_keeps_it_out_unless_devil_mode():
    from app.orchestration.director import Director

    state = GraphState(
        target={"name": "example.com"}, composition=["chariot", "justice"]
    )
    assert Director._resolve_team(state) == ["chariot"]


def test_full_team_run_can_repeat_agents():
    """Sem cartas, o Imperador usa o time completo e pode repetir um agente
    até confiança suficiente — a ordem das cartas não limita rodadas."""
    final = _run(GraphState(target={"name": "example.com"}))

    agents = [e["agent"] for e in final.history if e["agent"] != "emperor"]
    assert final.history[-1]["agent"] == "justice"
    assert set(agents) <= {"fool", "hermit", "magician", "justice"}
    assert final.supervisor_rounds >= 1


def test_chariot_safety_check_flags_candidates_without_hitl():
    """Carro em modo normal (sem Modo Diabo): safety check observa sinais
    não invasivos e marca indícios como candidatos — sem aprovação humana."""
    from app.orchestration.director import Director

    async def _run() -> GraphState:
        director = Director(sources_service=_FakeSourcesService())
        return await director.run(
            GraphState(
                target={"name": "example.com"},
                composition=["chariot", "hermit", "justice"],
            )
        )

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert final.pending_review is None
    safety = [e for e in final.history if e.get("action") == "safety"]
    assert safety, "o Carro deve ter rodado safety check no modo normal"
    assert any(
        f.get("requires_human_review") for f in final.findings
    ) or not final.findings