# Deploy no Railway — Argus Engine

> Guia de deploy do Argus Engine (backend FastAPI + frontend React) no Railway,
> como **dois serviços** no mesmo projeto: `backend` (API + banco SQLite) e
> `frontend` (nginx servindo a SPA e repassando `/api` ao backend via *private
> networking*). Mantém a topologia do `docker-compose.yml`, apenas trocando o
> proxy de borda (Traefik) pelo TLS gerenciado do Railway.

## 1. Pré-requisitos

- Repositório no GitHub (deploy conectado por branch, ou build manual).
- Duas definições de build já existem aqui:
  - `backend/Dockerfile` (+ `backend/railway.json`).
  - `frontend/Dockerfile` (+ `frontend/railway.json`).
- Um domínio autorizado para `ALLOWED_SCOPES` (alvos de pentest autorizado —
  sem ele, nenhum scan rodara).

## 2. Criar os serviços (Railway UI)

Para **cada** serviço: **New Service → GitHub repo → Root Directory** aponta para
a pasta do serviço. O `railway.json` força o builder `DOCKERFILE`.

| | backend | frontend |
|---|---|---|
| Root Directory | `backend` | `frontend` |
| Builder | `DOCKERFILE` (via railway.json) | `DOCKERFILE` (via railway.json) |
| Réplicas | **1** (obrigatório — ver §5) | 1 |
| Volume | `/app/data` (Ver §3) | — |
| Domain | Generate Domain → porta interna **8000** | Generate Domain → porta interna **80** |
| Health check (opcional) | `GET /health` | — |

> O backend escuta em `$PORT` (`${PORT:-8000}` no `CMD`). Mesmo assim, configure
> a porta interna correta em **Networking → Generate Domain**: o Railway roteia a
> primeira solicitação pela porta indicada.

## 3. Volume (persistência)

O filesystem do Railway é efêmero. Anexe um **Volume** ao serviço `backend`
montado em **`/app/data`** — ele cobre o banco SQLite (`./data/argus.db`), as
evidências (`data/evidence`) e o upload de scans. Sem isso, o banco reseta a cada
deploy.

## 4. Variáveis de ambiente

### Obrigatórias (backend)

| Variável | Valor / exemplo |
|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:////app/data/argus.db` |
| `EVIDENCE_DIR` | `/app/data/evidence` |
| `UI_PASSWORD` | senha do operador (protege toda rota; vazia = modo aberto) |
| `ARGUS_SESSION_SECRET` | segredo aleatório p/ assinar o cookie de sessão |
| `SESSION_COOKIE_SECURE` | `true` (Railway serve HTTPS) |
| `ALLOWED_SCOPES` | `["exemplo.com"]` — únicos alvos aceitos |
| `ARGUS_ENCRYPTION_KEY` | `Fernet.generate_key()` (32 bytes) — cifra chaves de API e rotação de senha |

Gere os segredos com:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
python -c "import secrets; print(secrets.token_urlsafe(48))"   # ARGUS_SESSION_SECRET
```

### Opcionais (backend)

- Chaves de LLM: `GROQ_API_KEY`, `OPENROUTER_API_KEY`, `OPENAI_API_KEY`,
  `GEMINI_API_KEY`. Sem chave, o gateway **degrada para simulado** (o run
  funciona, sem decisões de LLM reais).
- Chaves de fontes de intel: `NVD_API_KEY`, `ABUSEIPDB_API_KEY`,
  `URLSCAN_API_KEY`, `SHODAN_API_KEY`, `CENSYS_API_TOKEN`.
- Scanning: `SCAN_*`, `SCAN_DEPTH`, `CHARIOT_*` (defaults do
  `backend/.env.example` são válidos).
- `TOOLS_MANIFEST` default `tools.json` já é copiado para a imagem (via Dockerfile).

### Frontend

| Variável | Valor |
|---|---|
| `NGINX_BACKEND_HOST` | `backend.railway.internal:8000` — hostname DNS do **private networking** do Railway (nome do serviço `backend` + porta 8000, **sem** esquema) |

> O template `nginx.conf.template` usa `proxy_pass http://${NGINX_BACKEND_HOST}`
> e o entrypoint oficial do nginx substitui variáveis com prefixo `NGINX_`. No
> compose local o default (`backend:8000`) continua funcionando sem variável.

## 5. Restrições de arquitetura

- **1 réplica** no backend: lock de run único, rate-limit de `/auth/login` e
  cache do prefixo LLM são em memória e o banco é SQLite. Escalar quebra o lock e
  corrompe a single-instance design.
- **Tools CLI** (`whois`, `dig`, `echo`, etc.) não existem na imagem
  `python:3.13-slim` → degradam com `outcome: "failed"` (previsto e seguro).
  As **builtin** M2 (`http_request`, `session_login`, `form_discover`,
  `header_reprobe`) são puro HTTP e funcionam normalmente.
- **Sem sandbox Docker** de tools (`TOOL_SANDBOX` default `false`). Não ligue no
  Railway (sem Docker).
- **Migrações**: rodam automaticamente no boot (`lifespan` → `run_migrations`),
  inclusive recuperação de runs órfãos.
- **Ordem no primeiro deploy**: o nginx resolve `NGINX_BACKEND_HOST` na inicialização.
  Como o DNS interno (`backend.railway.internal`) só existe depois que o serviço
  `backend` provisiona, no **primeiro** deploy o frontend pode morrer antes do
  backend existir — resolva com **Redeploy** no serviço `frontend` assim que o
  backend estiver healthy. Deploys seguintes não sofrem disso.

## 6. Verificação pós-deploy

1. `GET https://<dominio>/health` → `{"status":"ok",...}` (proxied pelo frontend
   ou direto no domínio do backend).
2. Login na UI com `UI_PASSWORD`; criar um target dentro de `ALLOWED_SCOPES` e
   rodar um scan — verificar `summary.executive` no relatório.
3. Conferir logs do backend (migrações, recovery) e que o Volume montou
   (`/app/data/argus.db` gravado).