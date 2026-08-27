from __future__ import annotations

import os
from dataclasses import dataclass


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
