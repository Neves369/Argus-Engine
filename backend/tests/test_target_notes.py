from __future__ import annotations

from app.agents import get_archetype
from app.orchestration.state import GraphState


def test_context_includes_operator_observations():
    state = GraphState(target={"name": "example.com", "notes": "lab DVWA, creds admin/password"})
    context = get_archetype("hermit")._context(state)
    assert "lab DVWA, creds admin/password" in context
    assert "Operator observations:" in context


def test_context_omits_observations_when_empty():
    state = GraphState(target={"name": "example.com"})
    context = get_archetype("emperor")._context(state)
    assert "Operator observations" not in context


def test_context_omits_observations_when_blank():
    state = GraphState(target={"name": "example.com", "notes": "   "})
    context = get_archetype("fool")._context(state)
    assert "Operator observations" not in context


def test_emperor_prompt_mentions_observations():
    assert "observation" in get_archetype("emperor").system_prompt().lower()
