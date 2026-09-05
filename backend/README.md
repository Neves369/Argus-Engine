# Argus Engine — Backend

Backend de orquestração de agentes para **pentest e bug bounty autorizado** com scanning
ativo. Este serviço fornece a fundação (Etapa 0), o núcleo de orquestração em grafo
(Etapa 1) e scanning ativo (Etapa 12) do plano.

> **Uso autorizado apenas.** Este projeto só deve ser usado em alvos com autorização
> explícita e escopo definido, em conformidade com leis locais e políticas de bug bounty.

## Stack

- Python 3.11+ (testado em 3.13)
- FastAPI + Uvicorn
- SQLAlchemy 2.0 (async) + aiosqlite (SQLite)
- Pydantic v2 + pydantic-settings
- LangGraph (grafo de agentes com estado tipado)

## Estrutura

```
app/
├── main.py               # Entrypoint FastAPI
├── core/                 # config, logging, security (escopo + kill-switch)
├── db/                   # base, session, models (Target, Run, Finding, Evidence, ...)
├── schemas/              # Pydantic schemas
├── api/v1/               # router, targets, runs, sources, compositions
├── orchestration/        # state, graph, director
├── agents/               # BaseArchetype + arquetipos minimos
├── scanning/             # HTTP client, parsers, detecção de vulnerabilidades (Etapa 12)
├── llm/                  # gateway multi-provider (Etapa 3): client, providers, router
├── sources/              # fontes de dados externas plugadas (Etapa 9): registry + service
├── tools/                # tool registry + executor (Etapa 5)
└── services/
```

## Fontes de dados externas

Fontes de dados (CVE, OSINT, ...) fornecidas pelo operador são plugadas via manifesto
`sources.json` (configurado por `SOURCES_MANIFEST`), sem mudar o backend. Cada fonte
declara `url`, `fields` (campos retornados — minimização de dados), `ttl` e `rate_limit`.
Respostas são normalizadas e cacheadas no SQLite (`CveCache` / `ExternalDataCache`).
Sem fonte configurada ou em falha de rede, retorna dados simulados determinísticos.

## Setup

### Linux / macOS

```bash
cd backend
make setup            # cria .venv, instala deps, copia .env
source .venv/bin/activate
```

### Windows (PowerShell)

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
Copy-Item .env.example .env
New-Item -ItemType Directory -Force data
```

## Rodar

```bash
# aplica migrações (cria schema no banco)
make migrate          # ou: alembic upgrade head

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger: http://localhost:8000/docs
- Health:  http://localhost:8000/health

O banco é migrado automaticamente no startup (`alembic upgrade head`). Para gerar
uma nova migração após alterar models:

```bash
make revision m="descrição da mudança"   # ou: alembic revision --autogenerate
```

## Testes e lint

```bash
pytest
ruff check app tests
```

## Endpoints (fase 1)

| Método | Rota                  | Descrição                          |
|--------|-----------------------|------------------------------------|
| GET    | `/health`             | Status do serviço                  |
| GET    | `/policy`             | Política de uso autorizado (versionada) |
| POST   | `/api/v1/targets`     | Criar alvo                         |
| GET    | `/api/v1/targets`     | Listar alvos                       |
| GET    | `/api/v1/targets/{id}`| Buscar alvo                        |
| POST   | `/api/v1/runs`        | Criar e executar um run do grafo   |
| GET    | `/api/v1/runs`        | Listar runs                       |
| GET    | `/api/v1/sources`     | Listar fontes de dados externas   |
| POST   | `/api/v1/sources/{name}/query` | Consultar fonte (cache + minimização) |
| GET    | `/api/v1/runs/stream` | Executar um run com progresso em SSE (EventSource) |
| GET    | `/api/v1/runs/{id}`   | Status + estado final do run       |
| GET    | `/api/v1/runs/{id}/findings`  | Listar findings do run    |
| GET    | `/api/v1/runs/{id}/decisions` | Trilha de decisões do run |
| GET    | `/api/v1/runs/{id}/export`    | Exportar findings (JSON/Markdown) |
| PATCH  | `/api/v1/findings/{id}`       | Atualizar status de finding |
| POST   | `/api/v1/findings/{id}/validate` | Validar finding (pipeline de qualidade) |
| GET    | `/api/v1/findings/fp-rules`  | Listar regras de falso positivo (aprendidas + manuais) |
| POST   | `/api/v1/findings/fp-rules`  | Adicionar regra de falso positivo manual |
| PATCH  | `/api/v1/findings/fp-rules/{id}` | Ativar/desativar regra |
| DELETE | `/api/v1/findings/fp-rules/{id}` | Remover regra |
| POST   | `/api/v1/compositions` | Salvar composição de grafo (`sessions.config` + `validate_sequence`) |
| GET    | `/api/v1/compositions` | Listar composições                |
| GET    | `/api/v1/compositions/{id}` | Buscar composição             |
| DELETE | `/api/v1/compositions/{id}` | Remover composição            |
| POST   | `/api/v1/compositions/{id}/execute` | Resolver target + criar/executar run da composição |
| POST   | `/api/v1/findings/{id}/evidence` | Anexar evidência (arquivo + hash) |
| GET    | `/api/v1/tools`             | Listar ferramentas registradas    |
| POST   | `/api/v1/tools/{name}/invoke` | Invocar ferramenta (permissão + devil_mode) |

## LLM Gateway (Etapa 3)

Cliente unificado OpenAI-compatible (`app/llm/`) com os providers Groq, OpenRouter e
OpenAI. Configuração via env:

- `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY` — chaves de API (nunca commitadas).
- `EXECUTION_MODELS` — combos `"provider/model"` (sem restrição, usados com `DEVIL_MODE=true`).
- `JUDGMENT_MODELS` — combos `"provider/model"` (fixos/restritos, julgamento/investigação).

```python
from app.llm import LLMRouter, ChatMessage

router = LLMRouter()
result = await router.complete(
    [ChatMessage(role="user", content="...")],
    devil_mode=False,
    strategy="priority",
)
# result.provider, result.model, result.usage.tokens/cost, result.decision
```

## CLI (Typer/Rich)

```bash
argus compose validate PATH        # valida YAML/JSON de sequência
argus compose create NAME -a hermit,justice [--target NAME] [--devil-mode]
argus compose list
argus compose get ID
argus compose execute ID
argus compose export ID --out file.json|file.yaml   # JSON/YAML
argus run export ID --out file.csv                  # findings CSV
```

O entrypoint `argus` está declarado em `[project.scripts]`; a exportação reutiliza
`app.services.export` (composition_to_dict, run_to_dict, run_findings_csv).

## Próximas fases

- Etapa 5: Tool Registry — sandbox Docker
- Etapa 12: Scanning Ativo — módulo `app/scanning/`, HTTP client com rate limiting/timeout, integração com HermitAgent
