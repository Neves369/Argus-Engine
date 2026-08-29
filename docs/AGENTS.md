# AGENTS.md

Instruções para agentes de IA (Claude, Cursor, Codex, etc.) trabalhando neste repositório.

## Visão geral

**Argus Engine** — plataforma de orquestração de agentes para segurança ofensiva
**autorizada**. Backend Python (FastAPI + LangGraph + SQLite) e frontend React (Vite +
React Flow) com arquétipos visuais estilo tarô.

## Princípios inegociáveis (respeitar em toda mudança)

1. Uso exclusivo em alvos com autorização explícita e escopo definido.
2. Nenhum detalhe de técnicas de reconhecimento, exploração, payloads ou chaining —
   apenas arquitetura, abstração e fluxo de dados. **Relatar ≠ ensinar**: o relatório de
   segurança pode conter classe (CWE/OWASP), severidade (CVSS), CVE IDs, referência a
   exploit público e remediação; o que segue proibido é detalhar/ensinar a técnica
   ofensiva em si (ver `docs/adr/0005-reporting.md`).
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
  app/api/v1/   router, targets, runs, compositions, providers, dashboard
  app/orchestration/  state, graph, director, hitl
  app/agents/   BaseArchetype + 6 arquetipos (Imperador, Eremita, Louco, Justiça, Carro, Mago)
  app/services/ run_executor, persistence, export, run_control (lock + cancel)
frontend/       Vite + React + @xyflow/react (mock)
```

## Fluxo de execução (run único)

O sistema suporta **um run ativo por vez** (status `running` ou `pending_review`).
Ao mudar qualquer coisa no fluxo de execução, respeite:

- `backend/app/services/run_control.py` — lock de run único (`ensure_no_active_run` /
  `RunLockedError`) e cancelamento em memória (`request_cancel` / `is_cancel_requested`).
- O guard de lock deve ser aplicado em **todos** os pontos que criam Run:
  `POST /runs`, `GET /runs/stream`, `POST /compositions/{id}/execute`. Cliente que
  tentar iniciar com run ativo recebe `409`.
- `GET /runs/active` expõe o run ativo à UI (polling + restauração após refresh).
- **Auth leve da UI (Etapa 11 — hardening):** proteção por senha única de operador
  (`UI_PASSWORD`) + cookie de sessão assinado (`argus_session`, HMAC/HttpOnly/SameSite=Lax).
  Toda rota operacional é registrada em `app/api/v1/router.py` com
  `dependencies=[Depends(require_auth)]` (`app/api/deps.py`); se `UI_PASSWORD` estiver
  vazia, `require_auth` vira no-op (**modo aberto**). **Ao adicionar um novo router
  protegido, inclua-o em `router.py` — ele herda o guard automaticamente; não crie
  dependência manual por endpoint.** As rotas `/auth/*` e `/health` ficam de fora do guard.
  Frontend: `Login.tsx` + `client.ts` (`login`/`logout`/`getMe`, `credentials: 'include'`)
  e `App.tsx` (`handleLogin`/`handleLogout`/`handleMe`).
- `POST /runs/{id}/cancel` só válido para status `running`; o sinal é checado
  **entre nós** no generator do `/runs/stream` (o nó em execução termina antes do
  cancelamento efetivar).
- `GET /runs/stream` aceita `session_id` para executar uma composição salva pelo
  mesmo fluxo SSE usado no build manual — **não** usar `POST /compositions/{id}/execute`
  (síncrono) quando a UI precisar de log ao vivo/cancelamento.
- **Resultado final (Etapa 11 — relatório de segurança):** findings carregam
  substância de pentest — `severity` (real: critical/high/medium/low/info),
  `category` (CWE/OWASP), `cvss_score`/`cvss_vector`, `cves`, `known_exploits`,
  `remediation`, `evidence` e `references`. A origem é determinística
  (`app/services/demo_findings.py`, o "scanner simulado" — seam para as
  ferramentas/APIs reais), **não** texto livre do LLM. Severidade **não** é mais
  derivada da confiança. Relatório canônico em `GET /runs/{id}/report`; export em
  `GET /runs/{id}/export?format=markdown|json|csv|sarif`. Política de conteúdo:
  **relatar ≠ ensinar** (`docs/adr/0005-reporting.md`).
- **Ver runs antigos:** Dashboard (**Ver**) e Sessões (**Ver**) abrem o RunPanel em
  modo somente-leitura via `getReport(id)` no `App.tsx` (`openReport`/`finishRun`),
  que já traz `findings`/`summary`/`observability`/`trace`/`history`/`pending_review`.
  O painel também expõe botões de export (Markdown/JSON/CSV/SARIF) via
  `GET /runs/{id}/export` e, para runs `pending_review`, a UI de revisão HITL
  (**Aprovar**/**Rejeitar** → `POST /runs/{id}/review`) — loop HITL fechado na UI.

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
- Nos testes, runs que terminam `running`/`pending_review` são marcados `completed`
  no teardown (`_reset_active_runs` no `conftest.py`) para não travar o lock nos
  demais testes do mesmo banco.

## Ao implementar uma etapa

1. Leia a seção correspondente no `ROADMAP.md`.
2. Implemente seguindo a estrutura e convenções acima.
3. Rode `ruff` e `pytest` (backend) e `npm run lint`/`build` (frontend).
4. Atualize o `ROADMAP.md` marcando entregáveis concluídos e o status da etapa.

## Restrições de conteúdo

Não gerar, explicar ou detalhar: reconhecimento, validação, exploração, payloads,
chaining de vulnerabilidades ou qualquer técnica de hacking concreta. O trabalho fica no
nível de arquitetura de sistemas, abstração de ferramentas e fluxo de dados.
