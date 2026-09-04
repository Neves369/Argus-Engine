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

    # Economia de tokens (Etapa 7) — ambos DESLIGADOS por padrão. Veja
    # app/llm/compress.py e app/orchestration/graph.py.
    # Caveman: remove palavras de enchimento (artigos/conjunções) das mensagens
    # de saída para cortar tokens sem mudar a intenção.
    caveman_prompts: bool = False
    # Compressão de histórico entre nós: mantém o primeiro + os últimos N
    # registros e descarta o meio, reduzindo o contexto passado a cada agente.
    history_compression: bool = False
    history_keep_last: int = 8
    # Orçamento hard por agente (0 = desligado): além do orçamento do run
    # inteiro (`default_budget_tokens`/`default_budget_cost`), limita quanto
    # UM arquétipo específico pode consumir sozinho. Só tem efeito prático em
    # arquétipos que repetem (Eremita/Carro no modo padrão) — numa composição
    # customizada cada carta roda uma vez só. Ver `should_continue` em
    # app/orchestration/graph.py.
    budget_tokens_per_agent: int = 0
    budget_cost_per_agent: float = 0.0

    # Tool output compression ("RTK ou equivalente", Etapa 7): antes de um
    # resultado de tool/fonte entrar no contexto de um prompt, remove
    # ruído estrutural (chaves nulas/vazias, espaço em branco de JSON) sem
    # perder nenhum dado. Ver app/llm/compress.py::compact_tool_output.
    tool_output_compression: bool = False

    # Hardening (Etapa 10): resource limits applied to every CLI tool
    # subprocess (POSIX only — no-op elsewhere). See app/tools/executor.py.
    tool_subprocess_memory_limit_mb: int = 512
    tool_subprocess_max_output_bytes: int = 65_536

    cors_origins: list[str] = ["http://localhost:5173"]

    # Env var correspondente: ARGUS_ENCRYPTION_KEY (Fernet de 32 bytes).
    encryption_key: str = Field(default="", validation_alias="ARGUS_ENCRYPTION_KEY")

    # Login leve da UI: senha única do operador. Se vazia, a API fica em modo
    # aberto (dev). Env: UI_PASSWORD.
    ui_password: str = Field(default="", validation_alias="UI_PASSWORD")

    # Segredo para assinar o cookie de sessão. Se vazio, deriva de UI_PASSWORD.
    # Env: ARGUS_SESSION_SECRET.
    session_secret: str = Field(default="", validation_alias="ARGUS_SESSION_SECRET")


@lru_cache
def get_settings() -> Settings:
    return Settings()
