# Argus Engine — Backend

Backend de orquestração de agentes para **segurança ofensiva autorizada**. Este serviço
fornece a fundação (Etapa 0) e o núcleo de orquestração em grafo (Etapa 1) do plano.

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
├── db/                   # base, session, models (Target, Run)
├── schemas/              # Pydantic schemas
├── api/v1/               # router, targets, runs
├── orchestration/        # state, graph, director
├── agents/               # BaseArchetype + arquetipos minimos
├── llm/                  # placeholder (gateway multi-provider — Etapa 3)
├── tools/                # placeholder (registry — Etapa 5)
└── services/
```

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
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Swagger: http://localhost:8000/docs
- Health:  http://localhost:8000/health

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
| GET    | `/api/v1/runs`        | Listar runs                        |
| GET    | `/api/v1/runs/{id}`   | Status + estado final do run       |

## Próximas fases

- Etapa 2: 7 arquétipos Tarot completos (Imperador, Eremita, Louco, Justiça, Carro, Mago, Diabo)
- Etapa 3: LLM Gateway multi-provider (estilo OmniRoute)
- Etapa 4: Alembic + findings/evidence + exportação
- Etapa 5: Tool Registry + Sandbox
- SSE/WebSocket para o front acompanhar o grafo em tempo real
