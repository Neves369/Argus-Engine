# Plano de Melhoria — Argus Engine

**Objetivo:** elevar a profundidade dos achados de “recon + higiene HTTP” para cobertura real de **aplicação**, sem abandonar evidência observável, governança e uso autorizado.

**Contexto:** o run #23 em `pentest-ground.com:4280` (DVWA) produziu findings válidos de configuração e superfície (headers, cookies, HSTS, CT, DNS, RDAP, banner), mas não refletiu as classes que o laboratório existe para expor (CSRF, XSS, SQLi, Command Injection, File Inclusion, etc.).

**Princípios inegociáveis**
- Uso exclusivo em alvos com autorização explícita e escopo definido.
- Todo finding deve ter evidência observada (request/response, header, body, comportamento).
- Status padrão continua `candidate` até validação repetível + Justiça / HITL.
- Nada de exploração automática irrestrita; profundidade controlada por modo, arquétipo e flags.
- Tools destrutivas só com allowlist, sandbox e (quando aplicável) Diabo + HITL.

---

## 1. Diagnóstico do estado atual

### O que já funciona bem

| Camada | Capacidade |
|--------|------------|
| Sources | NVD, CVE.report, crt.sh, AbuseIPDB, urlscan, ip-api, HackerTarget, Shodan/InternetDB, Censys, RDAP, KEV |
| Scan | Crawl GET, robots, fingerprint, headers, cookies, HSTS, banner Server, forms, CORS |
| Findings | Derivação a partir de sources + scan; sempre `candidate` + revisão humana |
| Agentes | Imperador, Eremita, Louco, Carro, Mago, Justiça (+ Diabo no desenho) |
| Governança | Escopo, kill-switch, sandbox, orçamento de tokens, HITL, métricas |
| Ops | Prometheus / Grafana / Alertmanager, export de relatório |

### Gaps que explicam o relatório superficial

1. **Tools de aplicação quase inexistentes** — `tools.json` tem sobretudo `echo`, `fetch`, `whois`, `dig`.
2. **Scan ainda centrado em página + headers** — há esboço de autenticação e detector de formulários, mas não há ponte “superfície de app → teste controlado → evidência”.
3. **Pouca sessão autenticada reutilizável** entre agentes e probes.
4. **Findings de app não existem como classe** — só misconfig / info / superfície.
5. **Carro e Diabo subarmados** — sem tools úteis no manifest, o grafo não aprofunda.
6. **Relatório mistura pesos** — CT/RDAP e “headers ausentes” aparecem no mesmo nível narrativo que se esperaria de labs de aplicação.

---

## 2. Visão alvo (o que “bom o suficiente” significa)

Para um alvo tipo DVWA, em modo `depth=deep` autorizado, o relatório deve conter **três blocos claros**:

1. **Superfície e configuração** (o que já existe hoje, refinado)
2. **Aplicação — leads observáveis** (rotas/módulos, forms, parâmetros, erros verbosos, redirecionamentos observados, etc.)
3. **Correlação e validação** (CVE/KEV quando houver banner/produto real; Justiça promovendo só o que for repetível)

O sistema **não** precisa (nem deve) virar um exploit framework. Precisa gerar **leads densos e evidentes** que um operador humano (ou o Diabo sob HITL) possa aprofundar.

---

## 3. Plano por etapas

### Etapa M1 — Scan de aplicação observável (prioridade máxima)

**Objetivo:** mais findings úteis só com o que a resposta HTTP já mostra.

**Entregáveis**
- Sessão autenticada no `ScanService` (login form já parcialmente modelado) e reuso de cookie/header no crawl.
- Crawl ampliado para links internos do mesmo host (ex.: menu lateral DVWA).
- Novos detectores em `scanning/detectors.py`, sempre baseados em evidência:
  - formulários e campos sensíveis (ampliar `_input_vectors`)
  - parâmetros refletidos / mensagens de erro verbosas no body
  - redirecionamentos abertos observados na resposta
  - directory listing / pages de debug expostas (se presentes no body)
  - tecnologias/stack além do banner Server (quando identificáveis sem chute)
- `probe_url` consistente em todo finding de scan (já parcialmente feito).

**Pontos a discutir**
- Credenciais de lab: só via config explícita / secret store, nunca hardcoded no grafo.
- Limite de páginas por run (orçamento de tempo e gentleness).
- O que é “observado” vs “inferido” (manter a linha atual: só observado).

**Critério de aceite**
- Run em DVWA (`:4280`) produz findings de **aplicação** (forms/módulos/erros) além de headers/DNS.
- Nenhum finding sem evidência textual ligável a request/response.

**Arquivos principais**
- `backend/app/scanning/service.py`
- `backend/app/scanning/detectors.py`
- `backend/app/scanning/parsers.py`
- `backend/app/services/scan_findings.py`

---

### Etapa M2 — Tool Registry útil para HTTP/sessão

**Objetivo:** dar ao Carro (e depois ao Diabo) ferramentas reais, ainda não destrutivas.

**Entregáveis**
- Tools no `tools.json` (e specs):
  - `http_request` — GET/POST controlado, host allowlist, timeout, rate limit
  - `session_login` — obtém sessão a partir de credenciais autorizadas
  - `form_discover` — lista forms (action, method, fields) de uma URL
  - opcional: `http_header_probe` para revalidar misconfigs
- Executor suportando sessão (cookie jar por run) e bloqueio fora de escopo.
- Permissões por arquétipo: Eremita/Louco read-heavy; Carro probe; Diabo só com flag.

**Pontos a discutir**
- Onde vive o estado de sessão (GraphState vs ScanService vs ToolExecutor).
- Política de redirect e tamanho máximo de body armazenado como evidência.
- Diferença clara entre tool `destructive: false` e qualquer probe agressivo futuro.

**Critério de aceite**
- Carro consegue re-probe de `probe_url` e listar forms via tools do manifest.
- Tentativa fora de `ALLOWED_SCOPES` é bloqueada e logada.

**Arquivos principais**
- `backend/tools.json`
- `backend/app/tools/executor.py`
- `backend/app/tools/spec.py`
- `backend/app/agents/builtin.py` (Carro)

---

### Etapa M3 — Grafo com profundidade (`depth=quick|deep`)

**Objetivo:** o Imperador escolhe o quanto aprofundar; labs usam `deep`.

**Entregáveis**
- Parâmetro de run / composição: `depth`.
- Fluxo sugerido:
  - `quick`: sources + scan headers/superfície + Justiça leve
  - `deep`: autenticação → crawl de módulos → forms → probes Carro → Justiça
- HITL obrigatório antes de qualquer passo marcado como agressivo.
- Orçamento de tokens/páginas distinto por depth.

**Pontos a discutir**
- Default seguro (`quick`) vs opt-in `deep`.
- Como o front expõe depth na composição de arquétipos.
- Critérios de parada antecipada (pouca superfície, erros de auth, kill-switch).

**Critério de aceite**
- Mesmo alvo, `quick` e `deep` geram relatórios claramente diferentes em volume e tipo de finding.
- Imperador registra a decisão de depth no estado/auditoria.

**Arquivos principais**
- `backend/app/orchestration/graph.py`
- `backend/app/orchestration/director.py`
- `backend/app/agents/builtin.py` (Emperor)
- `backend/app/services/run_executor.py`

---

### Etapa M4 — Qualidade, Justiça e relatório

**Objetivo:** o relatório deixar de parecer “lista plana de info”.

**Entregáveis**
- Seções no export: Superfície | Configuração | Aplicação | Correlação CVE.
- Regras FP adicionais para ruído de lab/CDN.
- Justiça só promove a `validated` com:
  - evidência repetível (re-probe ok), e
  - confiança acima do limiar, e
  - (opcional) aprovação HITL em severidade média+.
- Campos de evidência mais ricos (método, URL, trecho de header/body, timestamp).

**Pontos a discutir**
- Severidade de “form encontrado” vs “misconfig de header” (taxonomia).
- Se findings de CT/RDAP devem ser `info` sempre e ir para apêndice.
- Formato PDF/Markdown: resumo executivo vs apêndice técnico.

**Critério de aceite**
- Relatório DVWA legível por seção; operador identifica imediatamente o que é config vs app.
- Taxa de `validated` baixa e justificada.

**Arquivos principais**
- `backend/app/services/export.py`
- `backend/app/services/judge.py`
- `backend/app/services/fp_rules.py`
- `backend/app/services/quality.py`

---

### Etapa M5 — Diabo controlado (opcional, depois de M1–M4)

**Objetivo:** stress controlado em escopo autorizado, nunca solto.

**Entregáveis**
- Flag `devil_mode` + HITL obrigatório.
- Allowlist estrita de tools para o Diabo.
- Limites duros de taxa, páginas e tempo.
- Todo passo do Diabo auditado e reversível via cancelamento.

**Pontos a discutir**
- O que o Diabo pode fazer que o Carro não pode (ainda sem virar exploração livre).
- Exigência de escopo assinado / nota de autorização no Target.
- Isolamento de evidências do Diabo no relatório.

**Critério de aceite**
- Sem `devil_mode`, nenhum caminho de código do Diabo executa probe extra.
- Com `devil_mode`, há trilha de auditoria completa.

---

## 4. Ordem recomendada de implementação

```
M1 (scan app observável)
 → M2 (tools HTTP/sessão)
   → M3 (depth no grafo)
     → M4 (relatório + Justiça)
       → M5 (Diabo controlado)
```

**MVP de “relatório menos superficial no DVWA”:** concluir **M1 + M2** e um export mínimo separado por seções (antecipação leve de M4).

---

## 5. Métricas de sucesso

| Métrica | Hoje (run #23) | Alvo pós M1–M2 |
|---------|----------------|----------------|
| Findings só de config/superfície | Dominam o relatório | Continuam, mas não sozinhos |
| Findings de aplicação com evidência | ~0 | ≥ alguns leads (forms, módulos, erros observados) |
| Findings sem `probe_url` / evidência | Raros no scan | Zero em scan/app |
| Runs `deep` vs `quick` | N/A | Comportamentos distintos |
| `validated` automático agressivo | Evitar | Continuar conservador |

---

## 6. Riscos e mitigação

| Risco | Mitigação |
|-------|-----------|
| Probe excessivo em lab compartilhado | Rate limit, robots, budget de páginas, depth default `quick` |
| Falso positivo de “vuln de app” | Só evidência observada; status `candidate`; Justiça rigorosa |
| Credenciais de lab vazando em log | Secrets, redaction, não logar password |
| Escopo ultrapassado | Allowlist de host, kill-switch, checagem antes de cada tool |
| Complexidade prematura no Diabo | M5 só depois de M1–M4 estáveis |

---

## 7. Checklist por etapa (para usar com agente de IA)

Em cada etapa, pedir ao agente:

1. Discutir os “Pontos a discutir” e registrar decisões (ADR se necessário).
2. Implementar o mínimo vertical (código + teste).
3. Rodar contra um alvo de lab autorizado (ex.: DVWA em pentest-ground) e anexar trecho de relatório.
4. Atualizar este plano com status (`feito` / `parcial` / `bloqueado`).
5. Não introduzir técnicas de exploração; manter evidência e governança.

---

## 8. Status inicial

| Etapa | Status | Notas |
|-------|--------|-------|
| M1 Scan app observável | Parcial | Detectores de aplicação implementados e testados; falta validação ao vivo no DVWA |
| M2 Tools HTTP/sessão | Parcial | Tools scanner implementadas e testadas; validação ao vivo pendente (compartilhada com M1) |
| M3 Depth no grafo | Parcial | `depth=quick\|deep` implementado e testado; validação ao vivo pendente (compartilhada) |
| M4 Relatório + Justiça | Parcial | Seções + validação conservadora implementadas e testadas; validação ao vivo pendente (compartilhada) |
| M5 Diabo controlado | Feito | Rails (allowlist + limites + auditoria) implementados e testados |

---

## 9. Próxima ação sugerida

**Etapa M1 — progresso registrado (2026-09-14):**

1. ✅ Sessão autenticada (`ScanService._authenticate`) + reuso de cookie no crawl — já existia, coberto em `tests/test_scanning_login.py`.
2. ✅ Crawl BFS de links internos do mesmo host — já existia, coberto em `tests/test_scanning.py`.
3. ✅ Detectores observáveis ampliados em `app/scanning/detectors.py`:
   - `_input_vectors` agora captura `select`/`textarea` (parser ampliado) e campos sensíveis (password/file/hidden);
   - novos detectores: erros verbosos (`_verbose_errors`), parâmetros refletidos (`_reflected_params`), meta-refresh para host externo (`_open_redirect_meta`), directory listing (`_directory_listing`) e stack/tecnologia (`_tech_identified`).
4. ✅ `derive_findings_from_scan` lista findings de aplicação + finding de **módulos/rotas** descobertos (`app/services/scan_findings.py`).
5. ⬜ Reexecutar run no DVWA autorizado e comparar com o run #23 (requer acesso ao lab).

**Etapa M2 — progresso registrado (2026-09-14):**

1. ✅ Novo `ToolKind.SCANNER` + campo `handler` no `ToolSpec` (`app/tools/spec.py`).
2. ✅ `tools.json` ganhou 4 tools não destrutivas: `http_request`, `session_login`,
   `form_discover`, `http_header_probe`.
3. ✅ `app/tools/http_tools.py` — `HttpToolHandler` com cookie jar por host/run,
   gate de `validate_scope` + kill-switch antes de cada request (fora de escopo →
   bloqueado e logado), reusando controles `SCAN_*` (rate/timeout/body-cap/UA/robots).
4. ✅ `ToolExecutor` com branch `SCANNER`; Carro (`_live_execution`) passa URL real
   (`probe_url`/target URL) para as tools scanner, não o nome do alvo.
5. ✅ `_select_login_form`/`_login_payload` movidos para `app/scanning/login.py`.
6. ✅ Testes em `tests/test_http_tools.py` (12): registro no manifesto, `http_request`
   GET/POST, `form_discover`, `http_header_probe`, `session_login` (reuso de cookie),
   fora de escopo bloqueado+logado, kill-switch, roteamento SCANNER do executor.

**Decisões M2 registradas (sem ADR, por escolha do operador):** sessão = cookie jar
dentro do `HttpToolHandler` (por run, nunca serializado no `GraphState`); redirect/body
= reusar controles do scanner (`ScanHTTPClient`, `max_redirects=5`, `scan_max_body_bytes`);
as 4 tools são `destructive:false` (`http_request` aceita POST apenas explícito, sem
payload de exploração); credenciais de login vêm de `SCAN_LOGIN_*` (nunca de params/log).

**Pendências de M1/M2:** validação ao vivo no DVWA autorizado (compartilhada) — exige
acesso ao lab + credenciais via config.

**Etapa M3 — progresso registrado (2026-09-14):**

1. ✅ `GraphState.depth` (default `"quick"`, serializado) + settings
   (`RUN_DEPTH`, `DEEP_SCAN_MAX_PAGES`, `DEEP_BUDGET_TOKENS/COST`) e
   `budget_for_depth()`.
2. ✅ `Director._resolve_team` inclui o **Carro** no time quando `depth="deep"`
   (além do Modo Diabo) — o deep ganha probes ao vivo + tools.
3. ✅ `ScanService.scan(target, max_pages=...)` aceita override de páginas;
   Eremita/Carro ampliam o crawl em `deep`.
4. ✅ Imperador registra `depth` em cada entry (auditoria); budgets de tokens/custo
   distintos por profundidade em runs/compositions/CLI.
5. ✅ API (`POST /runs`, `GET /runs/stream?depth=`, compositions) + CLI
   (`compose create --depth`) + schemas com `Literal["quick","deep"]`.
6. ✅ Testes em `tests/test_depth.py` (11): default quick, time inclui/exclui
   Carro por depth, orçamento distinto, crawl override, Imperador registra depth,
   quick sem chariot, API deep/quick/inválido.

**Decisões M3 registradas (sem ADR, por escolha do operador):** default seguro
`quick` (opt-in `deep`); a profundidade altera time (Carro), teto de páginas do
crawl e orçamento — nunca relaxa escopo/HITL/kill-switch; depth é persistido e
auditado pelo Imperador.

Quando M1–M3 estiverem validados ao vivo, seguir para **M4** (relatório por seções
+ Justiça conservadora).

**Etapa M4 — progresso registrado (2026-09-14):**

1. ✅ Seções no export (`app/services/export.py`): `finding_section()` classifica
   cada finding em **Superfície | Configuração | Aplicação | Correlação CVE**
   (por categoria, determinístico). `run_report` ganha `summary.by_section` e
   cada finding carrega `section` + `probe_url`; `run_report_markdown` e
   `run_report_pdf` agrupam por seção.
2. ✅ Validação conservadora (`app/services/quality.py`): `medium`+ exige HITL
   (`REVIEW_SEVERITY`); novo gate de **evidência repetível** — re-probe ao vivo
   confirmado OU evidência anexada; verificação refutada/pulada nunca valida.
3. ✅ Ruído de lab/CDN (`app/services/false_positives.py`): `BUILTIN_FP_NOISE`
   (proxy/data center, fingerprint de stack) mesclado ao pipeline em
   `findings.py`.
4. ✅ Finding de módulos/rotas recategorizado para "Aplicação" (vai para a seção
   Aplicação, não Superfície).
5. ✅ Testes em `tests/test_m4_report.py` (14): classificação por seção, resumo
   `by_section`, markdown agrupado, medium→review, refutado não valida,
   confirmado conta como evidência.

**Decisões M4 registradas (sem ADR, por escolha do operador):** taxonomia por
`category` (A06=correlação, A03/CWE-601=aplicação, A05/A02=configuração, resto
=superfície); severidade `info` de recon (CT/RDAP/stack) fica na seção Superfície
e não é promovida automaticamente (a taxa de `validated` segue baixa); `medium`+
sempre exige revisão humana.

Quando M1–M4 estiverem validados ao vivo, avaliar **M5** (Diabo controlado) — por
último, e só depois de M1–M4 estáveis.

**Etapa M5 — progresso registrado (2026-09-14):**

1. ✅ Rails do Diabo em `app/services/devil_guard.py` (`DevilGuard`): allowlist
   estrita de tools + limites duros (probes/taxa/tempo) + `audit()` serializável.
2. ✅ Config (`DEVIL_ALLOWED_TOOLS`, `DEVIL_MAX_PROBES`, `DEVIL_MAX_RATE`,
   `DEVIL_MAX_DURATION_SECONDS`).
3. ✅ `ChariotAgent._controlled_execution` registra os rails na **proposta de
   aprovação** (contexto + `proposal.devil_guard`) e no entry (`allowed_tools` +
   `devil_guard`) — trilha de auditoria completa.
4. ✅ Fronteira preservada: sem `devil_mode`, o Carro roda só `safety_check`
   (nenhum rail do Diabo é acionado).
5. ✅ **Backend de execução da allowlist**: após aprovação HITL, o Carro executa
   as tools permitidas via `ToolExecutor` com `devil_mode=True`, dentro dos rails
   (`max_probes`/`max_duration` + throttle real de `max_rate`), com trilha por
   passo (`devil_steps`) e kill-switch verificado a cada passo. `no_backend` vira
   só fallback (sem executor ou allowlist vazia). Contador `devil_probes_done`
   serializado no `GraphState`; `stop_reason` novo `devil_completed`/
   `devil_limits`/`devil_kill_switch`.
6. ✅ Testes em `tests/test_devil_guard.py` e `tests/test_devil_mode.py`:
   allowlist/resolve, throttle, execução da allowlist, tool destrutiva liberada,
   teto `max_probes`, kill-switch no meio, fallback `no_backend`.

**Decisões M5 registradas (sem ADR, por escolha do operador):** o Diabo executa
somente a allowlist sob os rails do `DevilGuard` (HITL obrigatório); exploração
livre segue fora de escopo. A allowlist é o teto de tools
(`http_request`/`form_discover`/`header_reprobe`/`session_login`); limites duros
de probes/taxa/tempo são codificados, aplicados e auditados, não apenas documentados.

**Estado final do plano:** M1–M5 implementados e testados. Pendência única
transversal: **validação ao vivo no DVWA autorizado** (compartilhada entre as
etapas) — exige acesso ao lab + credenciais via config/secret store.
