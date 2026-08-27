from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
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

    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
