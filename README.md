# Argus Engine

Plataforma de **pentest e bug bounty autorizado** com scanning ativo e
orquestração de agentes. Backend Python (FastAPI + LangGraph + SQLite) e frontend
React (Vite + React Flow) com arquétipos visuais estilo tarô.

> **Uso autorizado apenas.** Este projeto só deve ser usado em alvos com
> autorização explícita e escopo definido, em conformidade com leis locais e
> políticas de bug bounty. Ver [docs/SECURITY.md](docs/SECURITY.md).

## Repositório

```
backend/   FastAPI + LangGraph + SQLAlchemy (async) + SQLite
frontend/  Vite + React + React Flow (SPA)
docs/      RUNBOOK, ROADMAP, SECURITY, CONTRIBUTING, MANUAL_DO_USUARIO, ADRs
```

## Começando

```bash
# Backend (ver backend/README.md para detalhes)
cd backend
make setup          # cria .venv, instala deps, copia .env
source .venv/bin/activate
make migrate
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Frontend (em outro terminal)
cd frontend
npm ci
npm run dev         # UI em http://localhost:5173 (proxy /api -> :8000)
```

Alternativa com Docker (single-replica):

```bash
docker compose up -d --build   # UI em http://localhost:8080
```

Provisionar do zero também em `dev.sh`, que sobe o venv do backend e instala o
frontend.

## Documentação

- **docs/RUNBOOK.md** — operação: subir o serviço, configuração (`.env`, scopes,
  kill-switch, HITL, hardening), métricas `/metrics` e deploy de produção com
  TLS (Traefik + Let's Encrypt).
- **docs/ROADMAP.md** — plano vivo das etapas.
- **docs/SECURITY.md** — política de segurança e controles.
- **docs/CONTRIBUTING.md** — convenções e fluxo de desenvolvimento.
- **docs/MANUAL_DO_USUARIO.md** — como usar a UI.
- **docs/AGENTS.md** — instruções para agentes de IA trabalhando no código.
- **docs/adr/** — registros de decisão de arquitetura.

## Principais capacidades

- **Scanning ativo e orquestração de agentes** — um run por vez, grafo
  supervisionado de arquétipos, stream SSE ao vivo, retomada e cancelamento.
- **Governança**: escopo `ALLOWED_SCOPES`, kill-switch em runtime (one-way),
  sandbox de tools, cache e orçamento de tokens, auditoria via logs.
- **Auth da UI**: senha única de operador (`UI_PASSWORD`) com sessão assinada
  (HttpOnly/SameSite=Lax, opcional `Secure` em produção), rate-limit de login e
  rotação de senha.
- **Observabilidade**: métricas Prometheus em `/metrics`, relatório de segurança
  (CWE/OWASP, CVSS, CVEs) e exportação Markdown/JSON/CSV/SARIF/PDF.
- **CI/CD**: lint + testes (pytest, eslint/tsc, Playwright E2E), validação de
  compose, build de imagens Docker e release para GHCR em tags `v*`.

## Testes

```bash
# backend
cd backend && python -m pytest -q && ruff check app tests

# frontend
cd frontend && npm run lint && npm run build && npm test
npm run e2e                 # Playwright (back + front reais, determinístico)
```

## Licença

MIT — ver [LICENSE](LICENSE).