from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from app.agents import get_archetype
from app.agents.schemas import ArchetypeOutputBase
from app.orchestration.state import GraphState

EXPECTED_ARCHETYPES = {"emperor", "hermit", "fool", "justice", "chariot", "magician"}


@pytest.fixture(autouse=True)
def _no_api_keys(monkeypatch):
    """Force deterministic offline runs — schema contract must hold either way."""
    for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.mark.parametrize("key", sorted(EXPECTED_ARCHETYPES))
def test_every_archetype_declares_its_own_schema(key: str):
    agent = get_archetype(key)
    assert agent.output_schema is not ArchetypeOutputBase
    assert issubclass(agent.output_schema, ArchetypeOutputBase)


@pytest.mark.parametrize("key", sorted(EXPECTED_ARCHETYPES))
def test_archetype_history_entry_matches_its_schema(key: str):
    """The entry each archetype appends to history must satisfy output_schema."""
    agent = get_archetype(key)
    state = GraphState(target={"name": "example.com"})

    update = asyncio.run(agent.run(state))

    entry = update["history"][-1]
    # validate_entry() already ran inside run(); re-validating here proves the
    # *persisted* entry (post-validation) still round-trips through the schema.
    validated = agent.output_schema.model_validate(entry)
    assert validated.agent == key


def test_chariot_declined_entry_matches_schema(monkeypatch):
    """Chariot's non-execute branches (noop/declined) have a narrower shape."""
    from app.core.config import get_settings

    get_settings().devil_mode = True
    agent = get_archetype("chariot")

    state = GraphState(target={"name": "example.com"}, devil_mode=True)
    first = asyncio.run(agent.run(state))
    assert first["pending_review"]["kind"] == "destructive_action"

    state2 = state.model_copy(deep=True)
    state2.pending_review = first["pending_review"]
    state2.human_decision = {"id": first["pending_review"]["id"], "approved": False}
    second = asyncio.run(agent.run(state2))

    entry = second["history"][-1]
    validated = agent.output_schema.model_validate(entry)
    assert validated.action == "declined"

    get_settings().devil_mode = False  # reset shared singleton


def test_invalid_entry_is_rejected():
    agent = get_archetype("emperor")
    with pytest.raises(ValidationError):
        agent.validate_entry({"agent": "emperor"})  # missing required fields


def test_output_json_schema_is_a_valid_schema_document():
    for key in EXPECTED_ARCHETYPES:
        agent = get_archetype(key)
        schema = agent.output_json_schema()
        assert schema["type"] == "object"
        assert "agent" in schema["properties"]
        assert "action" in schema["properties"]


def test_list_archetypes_endpoint(client):
    response = client.get("/api/v1/archetypes")
    assert response.status_code == 200
    keys = {a["key"] for a in response.json()}
    assert keys == EXPECTED_ARCHETYPES


def test_archetype_schema_endpoint(client):
    response = client.get("/api/v1/archetypes/hermit/schema")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "object"
    assert "findings" in body["properties"]
    assert "sources_consulted" in body["properties"]


def test_archetype_schema_endpoint_unknown_key(client):
    response = client.get("/api/v1/archetypes/unknown/schema")
    assert response.status_code == 404
