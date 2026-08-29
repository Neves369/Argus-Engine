from __future__ import annotations

import os
from dataclasses import dataclass

# Cache de chaves resolvidas (provider -> chave decifrada).
# Preenchido na inicialização a partir do banco de dados e atualizado
# sempre que uma chave é salva via API. Caso esteja vazio, cai-se de volta
# ao ambiente (os.getenv), mantendo compatibilidade com testes e deployments
# que usam apenas as env vars.
_provider_key_overrides: dict[str, str] = {}

# Estado de habilitação por provider. Preenchido a partir do banco (ProviderConfig.enabled).
# Providers sem entrada no cache assumem habilitado=True, mantendo compatibilidade com
# deployments que usam apenas variáveis de ambiente.
_provider_enabled_overrides: dict[str, bool] = {}


def set_provider_api_key_override(provider: str, key: str) -> None:
    """Define uma chave override para um provedor (usa em vez do env var)."""
    _provider_key_overrides[provider] = key


def clear_provider_api_key_overrides() -> None:
    """Limpa todos os overrides — útil na reinicialização ou testes."""
    _provider_key_overrides.clear()


def set_provider_enabled_override(provider: str, enabled: bool) -> None:
    """Define o estado de habilitação de um provider (banco/configuração ativa)."""
    _provider_enabled_overrides[provider] = enabled


def clear_provider_enabled_overrides() -> None:
    """Limpa todos os estados de habilitação em memória."""
    _provider_enabled_overrides.clear()


def is_provider_enabled(name: str) -> bool:
    """Retorna se um provider está habilitado.

    Providers sem registro explícito no cache são tratados como habilitados,
    preservando o comportamento de deployments configurados via env vars.
    """
    return _provider_enabled_overrides.get(name, True)


@dataclass(frozen=True)
class ProviderSpec:
    name: str
    base_url: str
    api_key_env: str
    models: tuple[str, ...] = ()
    price_in: float = 0.0
    price_out: float = 0.0

    @property
    def api_key(self) -> str:
        # 1) override definido pelo serviço (banco de dados / configuração ativa)
        key = _provider_key_overrides.get(self.name)
        if key:
            return key
        # 2) ambiente (compatibilidade com testes e deployments tradicionais)
        key = os.getenv(self.api_key_env, "")
        if not key:
            raise ValueError(f"Missing API key: set {self.api_key_env}")
        return key


_PROVIDERS: dict[str, ProviderSpec] = {
    "groq": ProviderSpec(
        name="groq",
        base_url="https://api.groq.com/openai/v1",
        api_key_env="GROQ_API_KEY",
        models=("llama-3.3-70b-versatile", "llama-3.1-8b-instant"),
        price_in=0.59,
        price_out=0.79,
    ),
    "openrouter": ProviderSpec(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key_env="OPENROUTER_API_KEY",
        models=("openrouter/auto",),
        price_in=0.0,
        price_out=0.0,
    ),
    "openai": ProviderSpec(
        name="openai",
        base_url="https://api.openai.com/v1",
        api_key_env="OPENAI_API_KEY",
        models=("gpt-4o-mini",),
        price_in=0.15,
        price_out=0.60,
    ),
}


def get_provider(name: str) -> ProviderSpec:
    try:
        return _PROVIDERS[name]
    except KeyError:
        raise KeyError(f"Unknown provider: {name}") from None


def available_providers() -> list[str]:
    return list(_PROVIDERS)
