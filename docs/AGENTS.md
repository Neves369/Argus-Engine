# AGENTS.md

Instruções para agentes de IA (Claude, Cursor, Codex, etc.) trabalhando neste repositório.

## Visão geral

**Argus Engine** — plataforma de orquestração de agentes para segurança ofensiva
**autorizada**. Backend Python (FastAPI + LangGraph + SQLite) e frontend React (Vite +
React Flow) com arquétipos visuais estilo tarô.

## Princípios inegociáveis (respeitar em toda mudança)

1. Uso exclusivo em alvos com autorização explícita e escopo definido.
2. Nenhum detalhe de técnicas de reconhecimento, exploração, payloads ou chaining —
   apenas arquitetura, abstração e fluxo de dados.
3. Controles de segurança operacional, logging completo e kill-switch desde o dia 1.
4. Modelos abliterados apenas atrás de policy gateway + sandbox + HITL.
5. Economia de tokens e observabilidade desde o início.
6. Modo Diabo (execução real) só com escopo validado + sandbox + kill-switch + auditoria + HITL.

## Documentos obrigatórios de contexto

- `ROADMAP.md` — plano vivo; fonte de verdade das etapas (0 a 10).
- `SECURITY.md` — política de segurança e controles.
- `CONTRIBUTING.md` — convenções e fluxo.

## Estrutura

```
backend/        FastAPI + LangGraph + SQLAlchemy (async) + SQLite
  app/core/     config, logging, security (escopo + kill-switch)
  app/db/       base, session, models
  app/schemas/  Pydantic
  app/api/v1/   router, targets, runs
  app/orchestration/  state, graph, director
  app/agents/   BaseArchetype + 6 arquetipos (Imperador, Eremita, Louco, Justiça, Carro, Mago)
frontend/       Vite + React + @xyflow/react (mock)
```

## Comandos

Backend (PowerShell, dentro de `backend/`):

```powershell
.venv\Scripts\python.exe -m ruff check app tests
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Frontend (dentro de `frontend/`):

```bash
npm run lint
npm run build
npm run dev
```

## Convenções

- Python 3.11+, `ruff` como linter/formatador (config em `backend/pyproject.toml`).
- Estado do grafo é Pydantic `BaseModel` (`GraphState`), não `TypedDict` (evita bug de `typing_extensions`).
- Arquétipos herdam de `BaseArchetype` e são registrados em `app/agents/__init__.py`.
- Config via `.env` + pydantic-settings; nunca commitar segredos.
- Sem comentários desnecessários; sem emojis em código.

## Ao implementar uma etapa

1. Leia a seção correspondente no `ROADMAP.md`.
2. Implemente seguindo a estrutura e convenções acima.
3. Rode `ruff` e `pytest` (backend) e `npm run lint`/`build` (frontend).
4. Atualize o `ROADMAP.md` marcando entregáveis concluídos e o status da etapa.

## Restrições de conteúdo

Não gerar, explicar ou detalhar: reconhecimento, validação, exploração, payloads,
chaining de vulnerabilidades ou qualquer técnica de hacking concreta. O trabalho fica no
nível de arquitetura de sistemas, abstração de ferramentas e fluxo de dados.
