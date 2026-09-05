# Runbook de Operação — Argus Engine

> Este documento é para quem **opera** a plataforma (sobe o serviço, monitora runs,
> responde a incidentes) — não para quem desenvolve nela. Para arquitetura e
> decisões de design, ver `docs/adr/`. Para a política de uso autorizado, ver
> `docs/SECURITY.md`.

## 1. Visão geral

O Argus Engine é um serviço FastAPI + SQLite com um scheduler de grafo de agentes.
Não há workers separados nem filas externas: cada run executa dentro do próprio
processo da API. Isso simplifica operação (um processo para subir, um processo
para monitorar), mas também significa que **o processo da API é o único ponto de
falha** para runs em andamento — ver §7.1.

**Scanning ativo:** quando o alvo está dentro de `ALLOWED_SCOPES`, o sistema
realiza download de página, crawl, análise de headers/forms e detecção de
vulnerabilidades OWASP Top 10 — **independentemente do Modo Diabo**. O scanning
ativo é funcionalidade core (ver `docs/adr/0006-active-scanning.md`), com rate
limiting, timeout e self-imposed restrictions.

**Run único por vez:** a plataforma só permite **um run ativo por vez** (status
`running` ou `pending_review`). Qualquer tentativa de iniciar outro run nesse
estado retorna `409` (`POST /runs`, `GET /runs/stream`,
`POST /compositions/{id}/execute`). `GET /runs/active` informa qual run, se
houver, está ativo. Um run em `pending_review` sem decisão do operador mantém o
lock — comportamento esperado (um alvo por vez), não defeito; resolva a decisão
via §5 para liberar. Runs em execução podem ser cancelados com
`POST /runs/{id}/cancel` (válido só para `running`); o cancelamento efetiva
**entre nós** do grafo — o nó em andamento termina antes de parar.

**Conferir o resultado de um run:** pela UI, o painel de execução cai na aba
**Resultados** ao concluir (achados em primeiro plano com severidade, CVEs, exploit
público e remediação; tokens/custo ficam no apêndice "Observabilidade" recolhível).
Os achados também aparecem **ao vivo** durante a execução: o evento `node` do SSE
carrega `update.findings`, que a UI ingere direto no painel (não só no fim). O painel
de run traz ainda botões de **export** (Markdown/JSON/CSV/SARIF) que baixam o
relatório. Para runs antigos, use **Ver** no Dashboard ou em Sessões (abre o mesmo
painel em modo somente-leitura). Quando um run para em `pending_review` (Modo Diabo),
o painel mostra a **revisão humana** (contexto + proposta) com botões **Aprovar**/**
Rejeitar** (mapeia `POST /runs/{id}/review`); o Dashboard rotula a ação como
**Revisar** nesses casos. Pela API:
- `GET /runs/{id}/report` — **relatório estruturado** (`summary` + `findings[]` +
  `observability` + `trace` + `history` + `started_at`/`finished_at`/`duration_ms`),
  a forma canônica do "o que foi achado" (consumido pela UI em `finishRun`/`openReport`).
- `GET /runs/{id}/export?format=markdown` — relatório Markdown legível (severidade,
  CVSS, CVEs, exploits conhecidos, evidência, remediação, referências).
- `GET /runs/{id}/export?format=json|csv|sarif` — mesmo conteúdo em JSON/CSV/SARIF 2.1.0.
- `GET /runs/{id}` (estado final bruto, em `result`) e `GET /runs/{id}/findings`
  (achados persistidos com todos os campos de relatório).

Cada achado traz `severity` (critical/high/medium/low/info), `category` (CWE/OWASP),
`cvss_score`/`cvss_vector`, `cves`, `known_exploits` (referência a exploit público),
`remediation`, `evidence` e `references`. A política de conteúdo está em
`docs/adr/0005-reporting.md`: **relatar ≠ ensinar** — o relatório carrega inteligência
de vulnerabilidade, mas não detalha técnica/payload de exploração.

## 2. Subir o serviço

```bash
cd backend
make setup                       # cria .venv, instala deps, copia .env
source .venv/bin/activate
make migrate                     # aplica migrações Alembic (idempotente)
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Em produção, rode atrás de um supervisor (systemd, Docker + restart policy, etc.)
que reinicie o processo em caso de crash. O `alembic upgrade head` também roda
automaticamente no `lifespan` de startup do FastAPI — não é preciso rodá-lo à parte,
mas `make migrate` continua útil para aplicar a migração antes do primeiro boot
(evita a janela em que a API sobe e recebe tráfego antes do schema estar pronto).

**Checklist de pré-subida:**
- [ ] `.env` presente e revisado (nunca commitado — ver `.gitignore`)
- [ ] `ALLOWED_SCOPES` contém exatamente os alvos autorizados desta implantação
- [ ] `DEVIL_MODE` está no valor pretendido (`false` por padrão — ligar exige decisão operacional explícita, não só configuração)
- [ ] Diretório `data/` (banco + evidências) está em um volume persistente, não efêmero
- [ ] Chaves de provider LLM (`GROQ_API_KEY`, `OPENAI_API_KEY`, `OPENROUTER_API_KEY`, `GEMINI_API_KEY`) configuradas só para os providers realmente em uso

## 3. Configuração — variáveis mais operacionais

A lista completa está em `.env.example`; aqui só as que mais aparecem em operação:

| Variável | Efeito operacional |
|---|---|
| `KILL_SWITCH` | `true` interrompe qualquer run em andamento e bloqueia novos. Ver §6. |
| `FP_LEARNING` | `true` (default) aprende uma regra de falso positivo quando um finding é marcado `false_positive` (ver §6.6). |
| `FP_BLACKLIST` | Seed imutável de falsos positivos (JSON de strings, substring match sobre título+descrição). Regras aprendidas somam a este seed na validação. |
| `DEVIL_MODE` | Habilita o toggle de execução do `ChariotAgent` (ainda exige aprovação HITL por ação — ver §5). Não afeta scanning ativo, que roda sempre com escopo validado. |
| `ALLOWED_SCOPES` | Allowlist de alvos. Scanning ativo e OSINT rodam apenas contra alvos dentro desta lista. |
| `LLM_STRATEGY` | `priority`\|`fallback`\|`cost-optimized`\|`auto` — como o gateway ordena os providers. Trocar para `cost-optimized` é a alavanca mais rápida se o custo de LLM subir inesperadamente. |
| `GEMINI_API_KEY` | Chave do Google Gemini. O provider usa o endpoint OpenAI-compat da Google (`/v1beta/openai`), então aparece no Settings UI e em `GET /api/v1/providers` como os demais. Modelo default: `gemini/gemini-2.5-flash` (adicione em `EXECUTION_MODELS`/`JUDGMENT_MODELS` para usá-lo). |
| `LLM_CACHE_ENABLED` / `LLM_CACHE_TTL_SECONDS` | Cache de prefixo em memória (por processo). Desligar (`false`) se estiver depurando um provider e precisar garantir que toda chamada é real. |
| `CAVEMAN_PROMPTS` | `true` remove palavras de enchimento das mensagens enviadas aos providers (Economia de Tokens, Etapa 7). **Desligado por padrão.** |
| `HISTORY_COMPRESSION` / `HISTORY_KEEP_LAST` | `true` trunca o histórico entre nós do grafo (mantém o primeiro + últimos N=8 registros), cortando tokens de contexto. **Desligado por padrão** (opt-in). |
| `AGENT_PARALLEL` | `true` (default) executa em concorrência as pernas independentes de um nó (gateway + fontes + scan) — mesmo resultado, latência menor. Desligue se precisar serializar chamadas ao provider/ao alvo para depurar. |
| `TOOL_SUBPROCESS_MEMORY_LIMIT_MB` / `TOOL_SUBPROCESS_MAX_OUTPUT_BYTES` | Limites de recurso por invocação de tool CLI (§6.3). Suba o de memória se uma tool legítima estiver sendo matada por OOM do próprio limite. |
| `TOOL_SANDBOX` | `true` roda tools `kind: cli` em container Docker descartável (§6.7). **Default `false`.** Habilitar exige Docker no host e é fail-closed: sem Docker, a tool não roda. |
| `TOOL_SANDBOX_IMAGE` / `TOOL_SANDBOX_CPUS` / `TOOL_SANDBOX_PIDS_LIMIT` / `TOOL_SANDBOX_UID` | Defaults da sandbox (§6.7): imagem (`alpine:latest`), `--cpus` (1.0), `--pids-limit` (64) e uid não-root (65534). Override por tool no `tools.json` via `sandbox_image`/`sandbox_network`/`sandbox_user`. |
| `DATABASE_URL` | Aponta para o SQLite. Trocar exige rodar `alembic upgrade head` contra o novo arquivo antes do primeiro boot. |
| `EVIDENCE_DIR` | Onde os arquivos de evidência (hash SHA-256) são gravados. Precisa ser volume persistente e com backup — ver §7.2. |
| `UI_PASSWORD` | Se definida, a UI exige login com essa senha (cookie de sessão HMAC). Se vazia, a API roda em **modo aberto** (sem auth) — útil para dev/teste local, nunca para expor em rede. |
| `ARGUS_SESSION_SECRET` | Chave de assinatura do cookie de sessão. Se vazia, deriva de `UI_PASSWORD`; defina explicitamente em produção. |
| `SCAN_RATE_LIMIT` | Requisições por segundo ao alvo durante scanning ativo. Default: 10. |
| `SCAN_REQUEST_TIMEOUT` | Timeout em segundos por requisição HTTP ao alvo. Default: 10. |
| `SCAN_MAX_PAGES` | Número máximo de páginas crawleadas por scan (limite de escopo). Default: 10. |
| `SCAN_MAX_BODY_BYTES` | Teto de bytes do corpo de cada resposta baixada. Default: 512 KB. |
| `SCAN_RESPECT_ROBOTS` | `true` (default) faz o scanner respeitar `robots.txt` do alvo (self-imposed restriction). |
| `SCAN_EXTRA_HEADERS` / `SCAN_COOKIES` | Auth estática do scan (slice 1 de "login + scan"): headers extras em JSON (`{"Authorization":"Bearer ..."}`) e cookies de sessão (`session=abc; theme=dark`) aplicados a todo request ao alvo. Vazios por padrão. Credenciais vivem no env e **nunca** vão para log/relatório. |
| `SCAN_LOGIN_URL` / `SCAN_LOGIN_USERNAME` / `SCAN_LOGIN_PASSWORD` | Login dinâmico (slice 2 de "login + scan"): o scanner submete o form de login do alvo e reutiliza a sessão nos demais requests. Vazios por padrão. Falha no login **não** bloqueia o scan — vira nota no relatório (`report.auth`); só efetiva quando os três estão preenchidos. |

## 4. Kill-switch

- **Ligar:** `KILL_SWITCH=true` no `.env` + restart do processo, **ou** via runtime flag
  se exposta pela sua implantação (ver `app/core/security.py`).
- **Efeito:** todo novo nó do grafo recusa executar; runs em andamento param no
  próximo nó (não há rollback de ações já tomadas — o kill-switch impede *a
  próxima* ação, não desfaz a anterior).
- **Quando usar:** qualquer suspeita de comportamento fora de escopo, custo
  disparando sem explicação, ou incidente de segurança em andamento contra o
  próprio Argus Engine.
- **Desligar:** reverter a variável e reiniciar. Runs que pararam em `pending_review`
  ou no meio do grafo **não** retomam sozinhos — precisam ser revisados
  manualmente (`GET /api/v1/runs/{id}`) antes de decidir se devem continuar.

## 5. Human-in-the-Loop (fila de aprovação)

Toda ação destrutiva do `ChariotAgent` (Modo Diabo) e todo finding sinalizado pelo
`HermitAgent` como incerto param em `pending_review` até um operador decidir.

```bash
argus compose pending              # lista runs aguardando decisão
argus compose review RUN_ID --approve   # ou --reject
```

Ou via API: `POST /api/v1/runs/{id}/review` com `{"approved": true|false}`.

**Runbook — fila cheia / run parado sem explicação aparente:**
1. `GET /api/v1/runs/{id}` — confira `stop_reason` e `pending_review`.
2. Se `pending_review` não é `null`, é aprovação pendente — não é um bug.
3. Se `stop_reason` é `"declined"`, o operador já rejeitou anteriormente — o
   `ChariotAgent` não tenta de novo sozinho.
4. Nunca aprove uma ação sem ler o campo `context`/`proposal` do pending_review —
   ele é justamente o resumo pensado para essa decisão.

## 6. Controles de hardening (Etapa 10)

### 6.1 Redação de segredos em log e em prompts de LLM

`app/core/secrets.py` varre por padrões de segredo (chaves AWS, tokens GitHub/Slack,
JWT, blocos de chave privada, atribuições genéricas tipo `api_key=...`) em dois
pontos:

- **Todo log estruturado** (`app/core/logging.py`) — qualquer valor (mensagem ou
  campo `extra`) é redigido antes de virar JSON. Se um segredo aparecer em log
  mesmo assim, é sinal de um padrão novo não coberto — abra um ADR/issue para
  adicionar o padrão, não desative a redação.
- **Todo prompt enviado a um provider de LLM** (`app/llm/client.py`) — protege
  contra encaminhar sem querer uma credencial descoberta durante a investigação
  para um provider terceiro.

**Isso não se aplica à evidência armazenada** (`EvidenceStore`) — uma credencial
exposta é frequentemente exatamente o *finding* que a investigação existe para
documentar. Redigir ali destruiria a evidência. Tratamento de dados sensíveis em
evidência é política de retenção/acesso do operador, não desta camada.

**Runbook — suspeita de segredo vazado em log:**
1. Confirme se o padrão realmente deveria ter sido pego (`app/core/secrets.py::scan`);
   se sim, é um bug — corrija a redação primeiro, antes de mais nada.
2. Rotacione a credencial vazada imediatamente — a redação de log não desfaz uma
   exposição que já aconteceu antes dela existir (ex.: logs antigos, terminal do
   operador, histórico de shell).
3. Se o vazamento foi para um provider de LLM terceiro (não deveria acontecer após
   esta etapa, mas se a causa for um padrão não coberto), trate como incidente de
   dados com esse provider conforme os termos contratuais dele.

### 6.2 Timeout e cancelamento de subprocessos de tool

Toda tool `CLI` roda com timeout (`ToolSpec.timeout`, por tool). Ao estourar, o
processo filho é **morto** (`process.kill()`), não só abandonado — antes desta
etapa, o timeout cancelava a espera mas deixava o processo rodando em segundo
plano.

### 6.3 Limites de recurso do subprocesso

POSIX apenas (no-op no Windows). Aplicados via `preexec_fn` antes do `exec`:

- `RLIMIT_AS` (espaço de endereçamento) — `TOOL_SUBPROCESS_MEMORY_LIMIT_MB` (default 512MB)
- `RLIMIT_NOFILE` (descritores de arquivo) — fixo em 256

Saída (stdout/stderr) é truncada em `TOOL_SUBPROCESS_MAX_OUTPUT_BYTES` (default 64KB)
antes de entrar no histórico do run ou em qualquer log.

**Runbook — tool legítima sendo morta por limite de recurso:**
1. Confirme no `returncode` (não-zero, tipicamente `-9`/SIGKILL) e ausência de
   saída esperada que é OOM do rlimit, não bug da tool.
2. Suba `TOOL_SUBPROCESS_MEMORY_LIMIT_MB` no `.env` dessa implantação — é uma
   configuração por ambiente, não por tool individual (todas as tools CLI
   compartilham o mesmo teto).
3. Se a tool legitimamente precisa de muito mais memória que qualquer outra
   tool do ambiente, considere se ela deveria rodar fora do `ToolExecutor`
   (ex.: como fonte externa via `sources.json`) em vez de subir o teto global.

### 6.4 Cache de prefixo e compressão de prompt

Não são controles de segurança, mas de custo/latência — documentados aqui porque
compartilham a mesma camada (`app/llm/`). Ver `docs/ROADMAP.md` (Etapa 3) para o
funcionamento; `LLM_CACHE_ENABLED=false` é o botão de emergência se uma resposta
cacheada indevidamente virar suspeita durante um incidente.

### 6.5 Scanning Ativo — controles e limites

Scanning ativo é funcionalidade core — roda sempre que o alvo está em
`ALLOWED_SCOPES`, independentemente do Modo Diabo. Controles:

- **Rate limiting:** `SCAN_RATE_LIMIT` (default 10 req/s). Configure por
  ambiente; valores muito altos podem ser interpretados como ataque pelo alvo.
- **Timeout:** `SCAN_REQUEST_TIMEOUT` (default 10s). Requisições que excedem
  o timeout são canceladas.
- **Limite de páginas:** `SCAN_MAX_PAGES` (default 10) limita quantas páginas
  o crawl processa por scan; `SCAN_MAX_BODY_BYTES` (default 512 KB) limita o
  corpo de cada resposta baixada.
- **Self-imposed restrictions:** `SCAN_RESPECT_ROBOTS` (default `true`)
  faz o scanner respeitar `robots.txt`. Desativar só em ambientes controlados
  (labs, CTFs) onde `robots.txt` pode bloquear scanning legítimo.
- **Logging:** toda requisição HTTP ao alvo é logada (URL, status, duração).
- **Kill-switch:** `KILL_SWITCH=true` interrompe scanning em andamento.

**Runbook — scanning ativo bloqueado por robots.txt:**
1. Confirme que `SCAN_RESPECT_ROBOTS=true` (comportamento esperado).
2. Se o alvo é um lab/CTF/ambiente controlado, defina `SCAN_RESPECT_ROBOTS=false`.
3. Em produção, **nunca** desative self-imposed restrictions.

**Runbook — scanning ativo muito lento:**
1. Confirme `SCAN_RATE_LIMIT` — valores muito baixos (ex.: 1) causam lentidão.
2. Para labs/CTFs, suba o rate limit com cautela.
3. Verifique `SCAN_REQUEST_TIMEOUT` — timeouts muito curtos causam falhas em
   páginas lentas.

### 6.6 Local knowledge de falsos positivos (Etapa 6)

O Filtro de Qualidade suprime findings que casam com padrões de falso positivo
(substring sobre título + descrição). Os padrões vêm de duas fontes, mescladas
na validação:

- **Seed:** `FP_BLACKLIST` (env) — imutável, para conhecimento local estático.
- **Aprendidas:** decisões humanas. Marcar um finding como `false_positive`
  (`PATCH /findings/{id}`) extrai uma assinatura do título (≥ 4 caracteres,
  para não aprender ruído) e a persiste em `fp_rules` com `source="learned"`,
  `source_finding_id` e `hit_count`. Candidatos similares passam a ser
  suprimidos automaticamente; o `validate` incrementa `hit_count`.

Gestão via API (todas sob autenticação de operador):

| Método | Rota | Efeito |
|---|---|---|
| GET | `/api/v1/findings/fp-rules` | Listar regras (inclui `hit_count`) |
| POST | `/api/v1/findings/fp-rules` | Adicionar regra manual (`{"pattern": "..."}`) |
| PATCH | `/api/v1/findings/fp-rules/{id}` | Ativar/desativar (`{"enabled": bool}`) |
| DELETE | `/api/v1/findings/fp-rules/{id}` | Remover regra |

**Runbook — falso positivo recorrente:**
1. Identifique o título do finding que se repete.
2. Marque-o como `false_positive` (`PATCH /findings/{id}`) — o aprendizado age
   automaticamente; confirme a regra criada em `GET /findings/fp-rules`.
3. Se quiser suprimir também sem revalidar, adicione `POST /findings/fp-rules`
   com um padrão parcial do título.
4. Para desfazer, `DELETE /findings/fp-rules/{id}` (ou desative com `PATCH`).

**Runbook — regra aprendida agressiva demais:**
1. Confie no `hit_count`: regra com poucos hits pode ser genérica demais.
2. Desative a regra (`PATCH {"enabled": false}`) e revalide candidatos similares
   manualmente antes de removê-la.
3. Lembre: vereditos do LLM juiz **nunca** criam regra — só decisões humanas.

### 6.7 Sandbox de tools (Etapa 5)

Por padrão, tools `kind: cli` rodam como subprocesso direto (com timeout, rate
limit e limites de recurso — §6.2/§6.3). Com `TOOL_SANDBOX=true`, cada tool CLI
roda dentro de um **container Docker descartável** (`docker run --rm` de nome
`argus-sandbox-<uuid>`) com isolamento por padrão:

- Sem rede (`--network=none`), root filesystem read-only, `--cap-drop ALL`,
  `no-new-privileges`, `--pids-limit`/`--cpus`/`--memory`/`--memory-swap`
  limitados, usuário não-root (`nobody`, uid `TOOL_SANDBOX_UID`) e
  `--ulimit nofile=256:256`.
- Overrides por tool no `tools.json` (`ToolSpec`):
  - `sandbox_image` — imagem da tool (ex.: `python:3.12-alpine`);
  - `sandbox_network: true` — libera rede do container (se a tool precisar);
  - `sandbox_user` — usuário custom no container.
- **Fail-closed:** com sandbox habilitada e o Docker indisponível (binário ou
  daemon), a tool **não roda** e a invocação falha com erro claro — nunca há
  queda silenciosa para subprocesso sem isolamento.
- Timeout mata o container (`docker rm -f`) e remove o resíduo.

**Runbook — sandbox indisponível:**
1. Confira se `TOOL_SANDBOX=true` foi intencional; se não, desligue.
2. Valide o daemon: `docker version` e permissão do usuário do serviço.
3. Com sandbox obrigatória e daemon fora do ar, aguarde o serviço voltar — as
   invocações falharão até lá (por design).

**Runbook — "imagem não encontrada" / primeira execução lenta:**
1. O `docker run` faz pull automático; o pull conta no timeout da tool.
   Pré-puxe a imagem para não estourar: `docker pull <imagem>`.
2. Para tools específicas, defina `sandbox_image` no manifesto em vez de usar a
   default `TOOL_SANDBOX_IMAGE`.

**Runbook — tool CLI precisa de rede:**
1. Adicione `"sandbox_network": true` à tool no `tools.json`. Só o necessário —
   manter `--network=none` por padrão preserva o isolamento.

## 7. Dados: backup e recuperação

### 7.1 Banco (SQLite)

- Arquivo único em `DATABASE_URL` (default `data/argus.db`). Para backup a quente,
  use `sqlite3 data/argus.db ".backup data/argus.db.bak"` (não copie o arquivo
  bruto com o processo rodando — risco de captura em meio a uma escrita).
- Runs em andamento no momento do backup ficam com estado parcial no snapshot —
  isso é esperado; o estado do grafo é reconstruído a partir do que já foi
  persistido, não perdido, mas retomar exige o mesmo processo (§1: sem worker
  externo, um crash no meio de um run precisa de reprocessamento manual via API,
  não recuperação automática).

### 7.2 Evidências

- Arquivos em `EVIDENCE_DIR`, nomeados `{sha256}_{nome_original}`. O hash no nome
  permite verificar integridade a qualquer momento
  (`sha256sum` do arquivo deve bater com o prefixo do nome e com `Evidence.sha256`
  no banco).
- Faça backup do diretório de evidências **junto** com o banco, na mesma janela —
  os registros `Evidence` no banco apontam para caminhos nesse diretório; um
  restaurados de janelas diferentes pode deixar registros órfãos.

## 8. Logs

- Formato: JSON estruturado, um objeto por linha, em stdout (`app/core/logging.py`).
  Redigido (ver §6.1) antes de sair do processo.
- Campos padrão: `ts`, `level`, `logger`, `message`; campos extras variam por
  evento (ex. invocação de tool loga `tool`, `kind`, `destructive`, `devil_mode`,
  `duration_ms`).
- Nível controlado por `LOG_LEVEL` (`INFO` default). Suba para `DEBUG` só
  temporariamente ao investigar um incidente — não é recomendado como padrão de
  produção pelo volume gerado pelo gateway LLM.

## 9. Runbooks de incidente — índice rápido

| Sintoma | Seção |
|---|---|
| Run parado sem avançar | §5 |
| Não consigo iniciar um novo run (responde 409) | §1 (run único), §5 (`pending_review`) |
| Preciso parar um run em execução | §1 (`POST /runs/{id}/cancel`), §4 (kill-switch) |
| Custo de LLM subindo sem explicação | §3 (`LLM_STRATEGY=cost-optimized`), §6.4 |
| Segredo apareceu em log ou seria enviado a um provider | §6.1 |
| Tool trava ou consome recursos indevidamente | §6.2, §6.3 |
| Comportamento fora de escopo ou suspeita de segurança | §4 (kill-switch) |
| Precisa restaurar de um backup | §7 |
| UI pede login / sessão expira | §10 |
| Scanning ativo bloqueado por robots.txt | §6.5 |
| Scanning ativo muito lento ou com timeouts | §6.5 |
| Falso positivo recorrente / regra aprendida agressiva | §6.6 |

## 10. Autenticação leve da UI (Etapa 11 — hardening)

A API protege os endpoints operacionais com uma senha única de operador (não por
usuário). O fluxo é:

1. `POST /api/v1/auth/login` com `{"password": "..."}` → cookie `argus_session`
   assinado (HMAC), `HttpOnly`, `SameSite=Lax`, `Max-Age=28800` (8h).
2. Os demais endpoints exigem esse cookie via dependência `require_auth`
   (`app/api/deps.py`), aplicada a todos os routers em `app/api/v1/router.py`.
3. `GET /api/v1/auth/me` devolve `{authenticated, ui_enabled}` para a UI decidir
   se mostra o login; `POST /api/v1/auth/logout` limpa o cookie.

**Modo aberto:** se `UI_PASSWORD` estiver vazia, `require_auth` é desativado — a UI
entra direto, sem tela de login. Use só em dev/teste local. Em qualquer implantação
acessível por rede, defina `UI_PASSWORD` (e `ARGUS_SESSION_SECRET` explícito).

**Runbook — esqueceu a senha / quer deslogar todos:** como não há banco de usuários,
basta trocar `ARGUS_SESSION_SECRET` (ou `UI_PASSWORD`) e reiniciar — todos os cookies
existentes deixam de validar. Não há senha "esqueci" por design (operador único).

**Runbook — `409` no login:** significa que `UI_PASSWORD` não está definida (modo
aberto); não há o que autenticar — acesse a UI direto.

**Runbook — `401` no login:** senha incorreta. Não há bloqueio por tentativas (por
design, operador único); se suspeitar exposição, troque `UI_PASSWORD` e o segredo.
