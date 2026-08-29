from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_name: str = "Argus Engine"
    api_prefix: str = "/api/v1"
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./data/argus.db"

    log_level: str = "INFO"

    allowed_scopes: list[str] = []
    kill_switch: bool = False
    devil_mode: bool = False

    evidence_dir: str = "data/evidence"

    tools_manifest: str = "tools.json"

    sources_manifest: str = "sources.json"

    fp_blacklist: list[str] = []
    quality_score_threshold: float = 0.6

    default_budget_tokens: int = 100_000
    default_budget_cost: float = 1.0
    confidence_threshold: float = 0.6

    execution_models: list[str] = [
        "groq/llama-3.3-70b-versatile",
        "openrouter/openrouter/auto",
    ]
    judgment_models: list[str] = [
        "groq/llama-3.1-8b-instant",
        "openai/gpt-4o-mini",
    ]
    # Combo ordering strategy: "priority", "fallback", "cost-optimized" or "auto".
    # See app/llm/router.py:LLMRouter for the semantics of each.
    llm_strategy: str = "priority"

    # Prefix cache: serve identical (provider, model, messages) requests from
    # memory instead of re-calling the provider. See app/llm/cache.py.
    llm_cache_enabled: bool = True
    llm_cache_ttl_seconds: float = 300.0

    # Prompt compression: normalize whitespace and cap message length before
    # sending. 0/None disables length capping (whitespace normalization still
    # runs). See app/llm/compress.py.
    llm_max_prompt_chars: int = 8000

    # Hardening (Etapa 10): resource limits applied to every CLI tool
    # subprocess (POSIX only — no-op elsewhere). See app/tools/executor.py.
    tool_subprocess_memory_limit_mb: int = 512
    tool_subprocess_max_output_bytes: int = 65_536

    cors_origins: list[str] = ["http://localhost:5173"]

    # Env var correspondente: ARGUS_ENCRYPTION_KEY (Fernet de 32 bytes).
    encryption_key: str = Field(default="", validation_alias="ARGUS_ENCRYPTION_KEY")


@lru_cache
def get_settings() -> Settings:
    return Settings()
