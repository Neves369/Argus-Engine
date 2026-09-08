from __future__ import annotations

from functools import lru_cache

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Carrega o arquivo `.env` do diretório de trabalho para `os.environ`
# (override=False: variáveis já exportadas no ambiente ganham). O
# pydantic-settings lê `.env` apenas para os campos declarados no `Settings`;
# os resolvers de chaves de fontes de dados (app/sources/service.py) leem de
# `os.environ`, então sem isso as chaves do `.env` nunca chegariam a eles e
# toda fonte com autenticação degradaria para simulado silenciosamente.
load_dotenv()


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
    # Idade (segundos) a partir da qual um run `running`/`pending_review` é
    # tratado como órfão (processo anterior morreu sem finalizar) e recuperado
    # para `failed` — retomável pela UI. Ver app/services/run_recovery.py.
    run_stale_after_seconds: int = 86400

    # Supervisor (modo padrão, sem cartas): número máximo de rodadas em que o
    # Imperador pode delegar a um membro do time antes de fechar o run. Protege
    # contra loops infinitos quando o time não acumula confiança suficiente.
    supervisor_max_rounds: int = 8

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
    # Etapa 7 (resumo): quando a compressão está ligada, em vez de descartar o
    # meio, resume uma vez por run o trecho intermediário via LLM (degrade
    # determinístico quando o provider não responde). Ver app/llm/compress.py.
    history_llm_summary: bool = True
    # Orçamento hard por agente (0 = desligado): além do orçamento do run
    # inteiro (`default_budget_tokens`/`default_budget_cost`), limita quanto
    # UM arquétipo específico pode consumir sozinho. Só tem efeito prático em
    # arquétipos que repetem (Eremita/Carro no modo padrão) — numa composição
    # # Arquétipo(s) que repetem (Eremita/Carro no modo padrão) — numa composição
    # customizada cada carta roda uma vez só. Ver `budget_tokens_per_agent` em
    # `app.agents.builtin` (Imperador respeita o teto ao delegar).
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
    # Auth estática do scan ("login + scan", ROADMAP Etapa 12):
    # headers extras aplicados a todo request ao alvo (`SCAN_EXTRA_HEADERS`,
    # JSON: {"Authorization": "Bearer ..."}) e cookies de sessão
    # (`SCAN_COOKIES`, formato "a=b; c=d"). Mantém o scan funcional atrás de
    # alvos com sessão; credenciais ficam fora do relatório/log (ver
    # app/core/secrets.py).
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

    # Execução real do Carro (Etapa 15) — verificação ativa NÃO destrutiva.
    # O Carro re-prova ao vivo os achados candidatos (sondas GET dentro dos
    # controles do scanning ativo) e pode invocar tools NÃO destrutivas do
    # operador (TOOLS_MANIFEST, gating `destructive` da Etapa 5 mantido).
    # Master switch das sondas (`CHARIOT_VERIFY_ENABLED`) e teto de sondas por
    # run (`CHARIOT_VERIFY_MAX_PROBES`). Kill-switch/escopo/robots/rate-limit
    # do scan continuam valendo para cada sonda.
    chariot_verify_enabled: bool = True
    chariot_verify_max_probes: int = 10

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

    # Rate-limit do /auth/login (hardening): máximo de tentativas erradas por IP
    # dentro de uma janela em segundos; ultrapassou → 429 + Retry-After. Estado
    # em memória (single-process) — o contador zera no restart. O login correto
    # zera o contador do IP. Env: LOGIN_MAX_ATTEMPTS / LOGIN_WINDOW_SECONDS.
    login_max_attempts: int = 5
    login_window_seconds: int = 300
    # Tamanho mínimo da nova senha na rotação (POST /auth/password).
    ui_password_min_length: int = 8


@lru_cache
def get_settings() -> Settings:
    return Settings()
