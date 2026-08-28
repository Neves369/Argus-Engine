from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.orchestration.state import GraphState


def _utcnow() -> datetime:
    return datetime.now(UTC)


def request_approval(
    state: GraphState,
    *,
    kind: str,
    context: str,
    proposal: dict[str, Any] | None = None,
    next_node: str | None = None,
) -> dict[str, Any]:
    """Mark a run as awaiting human approval at a decision point.

    Returns the partial state update that sets ``pending_review`` and
    ``human_gate_next``. The graph router detects the pending review and
    halts at ``human_gate`` until ``/review`` answers it.
    """
    review_id = f"review-{len(state.review_log) + 1}"
    update: dict[str, Any] = {
        "pending_review": {
            "id": review_id,
            "kind": kind,
            "context": context,
            "proposal": proposal or {},
            "created_at": _utcnow().isoformat(),
        },
        "human_decision": None,
        "human_gate_next": next_node,
        "stop_reason": "pending_review",
        "next_agent": "human_gate",
    }
    return update


def is_answered(state: GraphState) -> bool:
    """True when the operator already answered the current pending review."""
    if state.pending_review is None or state.human_decision is None:
        return False
    return state.human_decision.get("id") == state.pending_review.get("id")


def is_awaiting_review(state: GraphState) -> bool:
    """True when the run is halted waiting for an operator decision."""
    return state.pending_review is not None and not is_answered(state)


def is_approved(state: GraphState) -> bool:
    if not is_answered(state):
        return False
    return bool(state.human_decision.get("approved"))


def resolve(state: GraphState) -> dict[str, Any]:
    """Consume a human decision via the gate node: clear pending_review, log the
    verdict and route to ``human_gate_next`` (or keep `next_agent` unset so the
    graph router decides).
    """
    pending = state.pending_review or {}
    decision = state.human_decision or {}
    log_entry = _log_entry(pending, decision)
    update: dict[str, Any] = {
        "pending_review": None,
        "human_decision": None,
        "review_log": [*state.review_log, log_entry],
        "stop_reason": None,
        "next_agent": state.human_gate_next,
    }
    return update


def consume(state: GraphState) -> dict[str, Any]:
    """Consume a human decision inline (e.g. inside an agent): log the verdict
    and clear pending_review, leaving routing to the graph router.
    """
    pending = state.pending_review or {}
    decision = state.human_decision or {}
    log_entry = _log_entry(pending, decision)
    return {
        "pending_review": None,
        "human_decision": None,
        "review_log": [*state.review_log, log_entry],
        "next_agent": None,
    }


def _log_entry(pending: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    verdict = "approved" if decision.get("approved") else "rejected"
    return {
        "id": pending.get("id"),
        "kind": pending.get("kind"),
        "verdict": verdict,
        "proposal": pending.get("proposal"),
        "note": decision.get("note"),
        "decided_at": _utcnow().isoformat(),
    }
