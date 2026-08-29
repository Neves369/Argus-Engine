from __future__ import annotations

import os

from fastapi import APIRouter, Body, HTTPException, status
from sqlalchemy import func, select

from app.api.deps import DBSession
from app.core.crypto import has_encryption
from app.db.models import AgentRun, ApiUsage, ProviderConfig
from app.db.session import async_session_factory
from app.llm.providers import (
    _provider_key_overrides,
    available_providers,
    get_provider,
    is_provider_enabled,
)
from app.services.provider_config import _load_overrides_from_db, set_api_key, set_enabled

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
async def list_providers() -> dict:
    """Lista os provedores de LLM configurados com metadados e status.

    Retorna:
    - provider: nome do provedor
    - base_url: URL base da API do provedor
    - models: tupla de modelos suportados
    - price_in / price_out: preços por 1000 tokens (do config do provedor)
    - has_api_key: boolean — há uma chave (cifrada ou env) registrada
    - key_source: origem da chave — "db" (cifrada), "env" ou null
    - enabled: boolean — provedor está ativo para uso
    - usage_tokens: tokens totais já consumidos (Agents + ApiUsage)
    - usage_cost: custo total já consumido (Agents + ApiUsage)
    """
    # Garante que o cache de overrides/habilitação está populado do banco
    if not _provider_key_overrides and has_encryption():
        await _load_overrides_from_db()

    # Providers com chave persistida no banco (não a partir de env)
    saved_providers: set[str] = set()
    if has_encryption():
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    select(ProviderConfig.provider).where(
                        ProviderConfig.api_key_encrypted.is_not(None),
                        ProviderConfig.api_key_encrypted != "",
                    )
                )
            ).scalars().all()
            saved_providers = set(rows)

    providers_info: list[dict] = []
    for name in available_providers():
        provider = get_provider(name)
        # Verifica se há chave cadastrada (no cache/override ou env)
        has_env_key = bool(os.getenv(f"{name.upper()}_API_KEY", ""))
        has_key = name in _provider_key_overrides or has_env_key
        key_source = "db" if name in saved_providers else ("env" if has_env_key else None)

        # Aggregation de uso real do banco
        async def _aggregate(
            db, name: str = name,
        ) -> dict:
            # Tokens e custo do ApiUsage (chamadas de API registradas)
            tokens_result = await db.execute(
                select(
                    func.coalesce(
                        func.sum(ApiUsage.prompt_tokens + ApiUsage.completion_tokens),
                        0,
                    )
                )
                .select_from(ApiUsage)
                .where(ApiUsage.provider == name)
            )
            tokens_row = tokens_result.scalar()
            cost_result = await db.execute(
                select(func.coalesce(func.sum(ApiUsage.cost), 0.0))
                .select_from(ApiUsage)
                .where(ApiUsage.provider == name)
            )
            cost_row = cost_result.scalar()

            # Tokens e custo do AgentRun (execuções de grafo)
            agent_tokens_result = await db.execute(
                select(func.coalesce(func.sum(AgentRun.tokens), 0))
                .select_from(AgentRun)
            )
            agent_tokens_row = agent_tokens_result.scalar()
            agent_cost_result = await db.execute(
                select(func.coalesce(func.sum(AgentRun.cost), 0.0))
                .select_from(AgentRun)
            )
            agent_cost_row = agent_cost_result.scalar()

            return {
                "tokens": int(tokens_row or 0),
                "cost": round(float(cost_row or 0.0), 6),
                "agent_tokens": int(agent_tokens_row or 0),
                "agent_cost": round(float(agent_cost_row or 0.0), 6),
            }

        async with async_session_factory() as db:
            agg = await _aggregate(db, name)

        providers_info.append(
            {
                "provider": provider.name,
                "base_url": provider.base_url,
                "models": provider.models,
                "price_in": provider.price_in,
                "price_out": provider.price_out,
                "has_api_key": has_key,
                "key_source": key_source,
                "enabled": is_provider_enabled(name),
                "usage_tokens": agg["tokens"] + agg["agent_tokens"],
                "usage_cost": round(float(agg["cost"] + agg["agent_cost"]), 6),
            }
        )

    return {
        "providers": providers_info,
        "has_encryption_configured": has_encryption(),
    }


@router.put("/{name}/api-key", status_code=status.HTTP_200_OK)
async def set_provider_api_key(
    name: str, key: str = Body(..., embed=True), db: DBSession = DBSession
) -> dict:
    """Cifra e salva a chave de API para o provedor especificado.

    A chave é cifrada usando Fernet (chave definida em ARGUS_ENCRYPTION_KEY do .env)
    e persistida no banco de dados. Após salvar, a chave passa a ser usada automaticamente
    pelas chamadas de LLM, substituindo a variável de ambiente.
    """
    try:
        await set_api_key(name, key, db)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return {"status": "ok", "provider": name, "message": "Chave salva e cifrada no banco"}


@router.put("/{name}/enabled", status_code=status.HTTP_200_OK)
async def set_provider_enabled(
    name: str, enabled: bool = Body(..., embed=True), db: DBSession = DBSession
) -> dict:
    """Ativa ou desativa um provedor.

    A chave armazenada é preservada; apenas o roteamento passa a ignorar um
    provedor desabilitado.
    """
    await set_enabled(name, enabled, db)
    return {"status": "ok", "provider": name, "enabled": enabled}