from __future__ import annotations

import asyncio

from app.agents import get_archetype
from app.core.config import get_settings
from app.orchestration.state import GraphState
from app.services.devil_guard import DevilGuard, build_devil_guard


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# DevilGuard — allowlist estrita + limites duros
# ---------------------------------------------------------------------------


def test_build_devil_guard_reads_settings():
    guard = build_devil_guard()
    assert guard.allowed_tools
    assert guard.max_probes > 0
    assert guard.max_rate > 0
    assert guard.max_duration_seconds > 0


def test_guard_allows_and_resolves_allowlist():
    guard = DevilGuard(
        allowed_tools=frozenset({"http_request", "form_discover"}),
        max_probes=5,
        max_rate=2.0,
        max_duration_seconds=60,
    )

    assert guard.allows("http_request") is True
    assert guard.allows("dig") is False
    assert guard.resolve_tools(["dig", "http_request", "whois", "form_discover"]) == [
        "http_request",
        "form_discover",
    ]


def test_guard_within_limits_enforces_caps():
    guard = DevilGuard(allowed_tools=frozenset(), max_probes=3, max_duration_seconds=10)

    assert guard.within_limits(0, 0.0) is True
    assert guard.within_limits(2, 5.0) is True
    assert guard.within_limits(3, 5.0) is False  # teto de probes
    assert guard.within_limits(0, 10.0) is False  # teto de tempo


def test_guard_audit_is_serializable():
    guard = DevilGuard(
        allowed_tools=frozenset({"http_request"}),
        max_probes=7,
        max_rate=1.5,
        max_duration_seconds=30,
    )
    audit = guard.audit()
    assert audit == {
        "allowed_tools": ["http_request"],
        "max_probes": 7,
        "max_rate_per_minute": 1.5,
        "max_duration_seconds": 30,
    }


# ---------------------------------------------------------------------------
# Carro em Modo Diabo — trilha de auditoria dos rails
# ---------------------------------------------------------------------------


def test_devil_approval_proposal_includes_guard_rails():
    settings = get_settings()
    original = settings.devil_mode
    settings.devil_mode = True
    try:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        result = _run(get_archetype("chariot").run(state))
    finally:
        settings.devil_mode = original

    pending = result["pending_review"]
    assert pending["kind"] == "destructive_action"
    rails = pending["proposal"]["devil_guard"]
    assert rails["allowed_tools"]
    assert rails["max_probes"] > 0
    assert rails["max_duration_seconds"] > 0


def test_devil_no_backend_entry_records_rails():
    settings = get_settings()
    original = settings.devil_mode
    settings.devil_mode = True
    try:
        state = GraphState(target={"name": "example.com"}, devil_mode=True)
        awaiting = _run(get_archetype("chariot").run(state))
        state2 = state.model_copy(deep=True)
        state2.pending_review = awaiting["pending_review"]
        state2.human_decision = {"id": awaiting["pending_review"]["id"], "approved": True}
        result = _run(get_archetype("chariot").run(state2))
    finally:
        settings.devil_mode = original

    entry = result["history"][-1]
    assert entry["action"] == "no_backend"
    assert entry["allowed_tools"]
    assert entry["devil_guard"]["max_probes"] > 0


def test_normal_mode_never_reaches_devil_guard():
    """Sem devil_mode o Carro faz apenas safety check — nenhum probe extra e
    nenhum rail do Diabo é acionado."""
    settings = get_settings()
    original = settings.devil_mode
    settings.devil_mode = False
    try:
        state = GraphState(target={"name": "example.com"}, devil_mode=False)
        result = _run(get_archetype("chariot").run(state))
    finally:
        settings.devil_mode = original

    entry = result["history"][-1]
    assert entry["action"] == "safety"
    assert "devil_guard" not in entry
