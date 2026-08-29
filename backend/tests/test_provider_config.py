from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from app.core.config import get_settings
from app.db.models import ApiUsage, ProviderConfig
from app.db.session import async_session_factory
from app.llm import ChatMessage, LLMRouter
from app.llm.providers import (
    clear_provider_api_key_overrides,
    clear_provider_enabled_overrides,
    is_provider_enabled,
    set_provider_enabled_override,
)


@pytest.fixture(autouse=True)
def _reset_provider_state():
    """Isola o estado em memória de chaves/enabled entre testes."""
    clear_provider_api_key_overrides()
    clear_provider_enabled_overrides()
    yield
    clear_provider_api_key_overrides()
    clear_provider_enabled_overrides()


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")


def _messages() -> list[ChatMessage]:
    return [ChatMessage(role="user", content="ping")]


def _ok_response(model: str, prompt: int = 1000, completion: int = 500) -> Response:
    return Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": "pong"}}],
            "usage": {
                "prompt_tokens": prompt,
                "completion_tokens": completion,
                "total_tokens": prompt + completion,
            },
        },
    )


def test_is_provider_enabled_defaults_true():
    assert is_provider_enabled("groq") is True
    assert is_provider_enabled("nao-existe") is True


def test_set_enabled_override_changes_state():
    set_provider_enabled_override("groq", False)
    assert is_provider_enabled("groq") is False
    set_provider_enabled_override("groq", True)
    assert is_provider_enabled("groq") is True


def test_route_for_mode_filters_disabled_providers():
    settings = get_settings()
    settings.execution_models = ["groq/exec-model", "openai/judge-model"]
    settings.judgment_models = ["openai/judge-model"]

    set_provider_enabled_override("groq", False)

    router = LLMRouter()
    assert router.route_for_mode(True) == [("openai", "judge-model")]


@respx.mock
def test_complete_skips_disabled_provider():
    settings = get_settings()
    settings.judgment_models = ["groq/fail-model", "openai/ok-model"]
    set_provider_enabled_override("groq", False)

    groq_route = respx.post(
        "https://api.groq.com/openai/v1/chat/completions"
    ).mock(return_value=_ok_response("fail-model"))
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_ok_response("ok-model")
    )

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    result = asyncio.run(_run())

    assert result.provider == "openai"
    assert result.model == "ok-model"
    assert groq_route.call_count == 0


@respx.mock
def test_complete_records_api_usage(client):
    # client garante que as migrações (e a tabela api_usage) já rodaram
    assert client.get("/api/v1/providers").status_code == 200

    settings = get_settings()
    settings.judgment_models = ["openai/usage-model-A"]

    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=_ok_response("usage-model-A")
    )

    async def _run() -> object:
        router = LLMRouter()
        try:
            return await router.complete(_messages(), devil_mode=False)
        finally:
            await router.close()

    result = asyncio.run(_run())
    assert result.usage.prompt_tokens == 1000
    assert result.usage.completion_tokens == 500

    async def _fetch_usage() -> list[ApiUsage]:
        async with async_session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(ApiUsage).where(ApiUsage.model == "usage-model-A")
                    )
                )
                .scalars()
                .all()
            )
            return [row for row in rows]

    rows = asyncio.run(_fetch_usage())
    assert len(rows) == 1
    row = rows[0]
    assert row.provider == "openai"
    assert row.prompt_tokens == 1000
    assert row.completion_tokens == 500
    assert row.run_id is None
    assert row.cost > 0


def test_gateway_endpoints_toggle_enabled(client):
    assert client.get("/api/v1/providers").json()["has_encryption_configured"] is False

    resp = client.put("/api/v1/providers/groq/enabled", json={"enabled": False})
    assert resp.status_code == 200

    body = client.get("/api/v1/providers").json()
    groq = next(p for p in body["providers"] if p["provider"] == "groq")
    assert groq["enabled"] is False

    # Reativa — o estado deve voltar a true
    client.put("/api/v1/providers/groq/enabled", json={"enabled": True})
    body = client.get("/api/v1/providers").json()
    groq = next(p for p in body["providers"] if p["provider"] == "groq")
    assert groq["enabled"] is True


def test_list_providers_reports_key_source(client):
    body = client.get("/api/v1/providers").json()

    by_name = {p["provider"]: p for p in body["providers"]}
    # GROQ_API_KEY/OPENAI_API_KEY definidos pela fixture → origem "env"
    assert by_name["groq"]["key_source"] == "env"
    assert by_name["groq"]["has_api_key"] is True
    # Sem env var e sem registro no banco → sem chave
    assert "openrouter" in by_name
    assert by_name["openrouter"]["key_source"] is None
    assert by_name["openrouter"]["has_api_key"] is False


def test_api_key_persists_to_db(client):
    resp = client.put(
        "/api/v1/providers/groq/api-key", json={"key": "sk-test-123"}
    )
    assert resp.status_code == 200

    body = client.get("/api/v1/providers").json()
    groq = next(p for p in body["providers"] if p["provider"] == "groq")
    assert groq["has_api_key"] is True
    assert groq["enabled"] is True

    async def _fetch_row() -> ProviderConfig | None:
        async with async_session_factory() as db:
            return await db.get(ProviderConfig, "groq")

    row = asyncio.run(_fetch_row())
    assert row is not None
    # Sem ARGUS_ENCRYPTION_KEY o valor é persistido em claro (dev), apenas para testes
    assert row.api_key_encrypted == "sk-test-123"
    assert row.enabled is True