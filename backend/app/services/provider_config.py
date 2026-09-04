from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crypto import decrypt_secret, encrypt_secret, has_encryption
from app.db.models import ProviderConfig
from app.db.session import async_session_factory
from app.llm.providers import (
    _provider_key_overrides,
    clear_provider_api_key_overrides,
    clear_provider_enabled_overrides,
    set_provider_api_key_override,
    set_provider_enabled_override,
)


async def _load_overrides_from_db() -> None:
    """Carrega chaves criptografadas e estados de habilitação do banco para a memória."""
    clear_provider_api_key_overrides()
    clear_provider_enabled_overrides()
    async with async_session_factory() as db:
        result = await db.execute(select(ProviderConfig))
        rows = result.scalars().all()
        for row in rows:
            set_provider_enabled_override(row.provider, row.enabled)
            if row.api_key_encrypted and has_encryption():
                try:
                    plain = decrypt_secret(row.api_key_encrypted)
                    if plain:
                        set_provider_api_key_override(row.provider, plain)
                except Exception:
                    pass


async def get_api_key(provider: str, db: AsyncSession | None = None) -> str:
    """Retorna a chave de API para o provedor.

    Ordem de prioridade:
    1) Chave salva e cifrada no banco de dados (se existir e estiver disponível);
    2) Variável de ambiente (GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY);
    3) Levanta ValueError se nenhuma estiver configurada.
    """
    # Garante que o cache está populado
    if not _provider_key_overrides and has_encryption():
        await _load_overrides_from_db()

    # 1) Cache em memória (preenchido do DB)
    if provider in _provider_key_overrides:
        return _provider_key_overrides[provider]

    # 2) Variável de ambiente
    key = os.getenv(f"{provider.upper()}_API_KEY", "")
    if key:
        set_provider_api_key_override(provider, key)
        return key

    # 3) Nada encontrado — levantamento controlado
    raise ValueError(f"Missing API key for {provider}: set {provider.upper()}_API_KEY env var")


async def set_api_key(provider: str, key: str, db: AsyncSession) -> None:
    """Cifra e salva a chave de API no banco de dados para o provedor informado."""
    # Atualiza o cache em memória
    set_provider_api_key_override(provider, key)
    set_provider_enabled_override(provider, True)

    # Cifra a chave
    if has_encryption():
        cipher = encrypt_secret(key)
    else:
        # Se criptografia não estiver configurada, armazena em claro (desenvolvimento)
        cipher = key

    # Upsert no banco
    await db.merge(
        ProviderConfig(
            provider=provider,
            api_key_encrypted=cipher,
            enabled=True,
        )
    )
    await db.flush()
    await db.commit()


async def set_enabled(provider: str, enabled: bool, db: AsyncSession) -> None:
    """Ativa ou desativa um provedor, preservando a chave salva no registro."""
    # Atualiza o cache em memória
    set_provider_enabled_override(provider, enabled)
    # Atualiza apenas a coluna enabled — a chave armazenada é preservada
    row = await db.get(ProviderConfig, provider)
    if row is None:
        db.add(ProviderConfig(provider=provider, enabled=enabled))
    else:
        row.enabled = enabled
    await db.flush()
    await db.commit()


async def list_configs() -> list[dict]:
    """Retorna a lista de configs de provedores (metadados, sem expor a chave real)."""
    async with async_session_factory() as db:
        result = await db.execute(select(ProviderConfig))
        rows = result.scalars().all()
    result: list[dict] = []
    for row in rows:
        has_key = row.api_key_encrypted is not None if has_encryption() else False
        result.append(
            {
                "provider": row.provider,
                "enabled": row.enabled,
                "has_api_key": has_key,
            }
        )
    return result