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
    # Aprender regras de falso positivo a partir de decisões humanas (PATCH
    # /findings/{id} -> false_positive) e persisti-las em `fp_rules`.
    # `FP_BLACKLIST` continua como seed imutável, mesclada com as regras
    # aprendidas no momento da validação.
    fp_learning: bool = True
    quality_score_threshold: float = 0.6

    default_budget_tokens: int = 100_000
    default_budget_cost: float = 1.0
    confidence_threshold: float = 0.6

    # Execução paralela básica (Etapa 1): executa em concorrência as pernas
    # independentes de um nó (gateway LLM + coleta de fontes + scan ativo no
    # Eremita; gateway + fontes no Louco) — `asyncio.gather` preserva a ordem,
    # então o resultado é idêntico ao sequencial. Default: on (latência menor).
    agent_parallel: bool = True

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

    # Sandbox Docker (Etapa 5, ver docs/adr/0007-tool-sandbox.md): executa
    # tools CLI dentro de um container descartável em vez de subprocesso
    # direto. Opt-in (default desligado). Quando habilitado e o Docker estiver
    # indisponível, a tool NÃO roda (fail-closed) — nunca cai silenciosamente
    # para subprocesso sem isolamento.
    tool_sandbox: bool = False
    tool_sandbox_image: str = "alpine:latest"
    tool_sandbox_cpus: float = 1.0
    tool_sandbox_pids_limit: int = 64
    tool_sandbox_uid: int = 65534

    # Scanning ativo (Etapa 12) — ver docs/adr/0006-active-scanning.md.
    # Rate limit de requisições ao alvo por minuto (`SCAN_RATE_LIMIT`).
    scan_rate_limit: float = 10.0
    # Timeout por requisição ao alvo em segundos (`SCAN_REQUEST_TIMEOUT`).
    scan_request_timeout: float = 10.0
    # Número máximo de páginas crawleadas por scan (`SCAN_MAX_PAGES`).
    scan_max_pages: int = 10
    # Teto de bytes do corpo de cada resposta (`SCAN_MAX_BODY_BYTES`).
    scan_max_body_bytes: int = 512_000
    # Respeitar robots.txt (self-imposed restriction) (`SCAN_RESPECT_ROBOTS`).
    scan_respect_robots: bool = True
    # User-Agent usado nas requisições ao alvo (`SCAN_USER_AGENT`).
    scan_user_agent: str = "ArgusEngine/0.1 (authorized scanning)"
    # Auth estática do scan (slice 1 de "login + scan", ROADMAP Etapa 12):
    # headers extras aplicados a todo request ao alvo (`SCAN_EXTRA_HEADERS`,
    # JSON: {"Authorization": "Bearer ..."}) e cookies de sessão
    # (`SCAN_COOKIES`, formato "a=b; c=d"). Mantém o scan funcional atrás de
    # alvos com sessão; credenciais ficam fora do relatório/log (ver
    # app/core/secrets.py). Login dinâmico (form) = slice 2, ainda não feito.
    scan_extra_headers: dict[str, str] = {}
    scan_cookies: str = ""
    # Login dinâmico do scan (slice 2 de "login + scan"): o scanner submete o
    # form de login do alvo (`SCAN_LOGIN_URL`) com essas credenciais e reutiliza
    # a sessão nos demais requests. Vazio = desligado. Credenciais vivem no env
    # e nunca entram em log/relatório. Falha no login não bloqueia o scan —
    # vira nota no relatório (`report.auth`).
    scan_login_url: str = ""
    scan_login_username: str = ""
    scan_login_password: str = ""

    # Correlação CVE por fingerprint (Etapa 13 — integração de ferramentas):
    # teto de candidatos devolvidos pelo NVD keyword search por produto/versão.
    # Correlação é lead textual (status="candidate", requires_human_review=True);
    # valor alto só aumenta ruído, não precisão.
    cve_correlate_max_cves: int = 5

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
