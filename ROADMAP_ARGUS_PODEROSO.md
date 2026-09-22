# Roadmap — Argus Engine Poderoso

**Objetivo:** transformar o Argus de orquestrador com recon + mapa de aplicação em uma **plataforma poderosa de avaliação autorizada** — densa em sinal, baixa em ruído, auditável e segura de operar.

**Não-objetivo:** virar exploit framework autônomo ou substituir pentest humano sem evidência e sem escopo.

**Estado de partida (set/2026)**
- M1 validado no DVWA (run #7): superfície, config, forms, rotas, reflexão, erros verbosos, relatório por seções.
- Próximo imediato: polish de relatório + M2 (tools HTTP/sessão + re-probe do Carro).
- M3–M5 do plano anterior continuam válidos; este documento **estende** o horizonte.
- **M6 P0 entregue (set/2026):** proactive probes de comportamento sob política no run (ver seção M6).
- **M6 P1 entregue (set/2026):** injeção (replay controlado) + upload (observação de form), com allowlist de classes por run.
- **M6 P2 entregue (set/2026):** CSRF (POST de estado sem token) + redirect aberto reproduzível (inclui observação de redirect 3xx no scan).
- **M6 P3 entregue (set/2026):** authn fraca — login com resposta diferencial (enumeração de usuário) com controles sentinela, sem brute force.
- **M7 P0 entregue (set/2026):** sessão única com consciência de sessão — pages etiquetadas ("user"/"anon"), metadados de sessão no relatório e constatação de "visível apenas em sessão autenticada" via baseline anônimo (ver seção M7).
- **M7 P1 entregue (set/2026):** múltiplos perfis de sessão (`SCAN_SESSION_PROFILES`) com clients isolados e diferença de acesso entre papéis — "acesso distinto entre sessões" (ver seção M7).

**Princípios**
1. Uso apenas em alvos autorizados, com escopo e kill-switch.
2. Finding sem evidência observável não entra no relatório.
3. `candidate` é o padrão; `validated` exige reprodução e regras da Justiça (e HITL quando a severidade subir).
4. Profundidade é opt-in (`depth`, flags, Diabo), nunca surpresa.
5. O operador manda: o grafo sugere e prioriza; o humano confirma o que importa.

---

## Visão de produto

O Argus poderoso entrega, em um run autorizado:

| Camada | Resultado para o operador |
|--------|---------------------------|
| Superfície | O que existe (DNS, CT, hosts, stack) |
| Configuração | Higiene HTTP/TLS/cookies/banner |
| Aplicação — mapa | Rotas, forms, parâmetros, erros expostos |
| Aplicação — comportamento | Sinais repetíveis após probes **controlados** |
| Correlação | CVE/KEV ligados a produtos/versões observados |
| Decisão | Prioridade, confiança, o que revisar manualmente |

**Posicionamento:** assistente de avaliação / bug bounty / lab que **reduz tempo até o achado relevante**, não robô que “hackeia sozinho”.

---

## Mapa das fases

```text
[Já feito]     M1  Scan observável de app
[Imediato]     M1b Polish de relatório + agregação
[Curto]        M2  Tools HTTP/sessão + re-probe (Carro)
[Curto]        M3  depth=quick|deep
[Médio]        M4  Justiça, FP, relatório maduro
[Médio]        M5  Diabo controlado (HITL)
[Poder]        M6  Probes de comportamento por classe (controlados) — P0..P3 pronto
[Poder]        M7  Sessão, papéis e fluxos multi-step
[Poder]        M8  APIs e superfícies modernas
[Escala]       M9  Qualidade, baseline, multi-alvo, CI
[Produto]      M10 UX operador, políticas, pacotes de escopo
```

---

## Fase M1b — Polish de relatório (imediato)

**Meta:** o run #7 legível sem 14 findings iguais de form.

**Entregas**
- Agregar forms em um finding com tabela na evidência.
- Filtrar estáticos do contador de módulos.
- Resumo executivo (counts por seção, auth, depth).
- Categorias estáveis na seção Aplicação.

**Aceite**
- Mesmo conteúdo informativo do #7 em bem menos itens “copy-paste”.
- `probe_url` / detalhes estruturados preservados para o Carro.

---

## Fase M2 — Tools e re-probe

**Meta:** o Carro confirma que o lead ainda existe ao vivo.

**Entregas**
- `http_request`, `session_login`, `form_discover` (não destrutivos).
- Cookie jar por run; bloqueio fora de escopo.
- Re-probe dos leads de erro verboso, reflexão e sample de forms/rotas.
- Evidência com histórico de probe (timestamp, status, trecho).

**Aceite**
- Run `deep` mostra re-probe ok/falha nos leads tocados.
- Zero tool fora de allowlist de host.

---

## Fase M3 — Profundidade explícita

**Meta:** o operador escolhe o custo/benefício.

| Depth | Comportamento |
|-------|----------------|
| `quick` | Sources + scan config/superfície + sample mínimo de app |
| `deep` | Auth + crawl amplo + forms/rotas + re-probe Carro + probes M6 (P0 default; P1/P2/P3 via allowlist `probe_classes`) |
| `deep+` (futuro, após M7) | Inclui classes de sessão/authz dentro da política |

**Aceite**
- Default seguro = `quick`.
- Decisão de depth auditada no estado do run.

---

## Fase M4 — Justiça e confiança

**Meta:** pouco `validated`, muito sinal confiável.

**Entregas**
- Regras de promoção: evidência repetida + limiar de confiança (+ HITL se severidade ≥ low/medium).
- FP rules (CDN, labs, headers esperados em certos stacks).
- Confidence score documentado (o que sobe/desce o número).
- Export: Superfície | Configuração | Aplicação | Comportamento | Correlação CVE.

**Aceite**
- Taxa de `validated` baixa e explicável.
- Operador entende por que um item ficou `candidate`.

---

## Fase M5 — Diabo controlado

**Meta:** pressão extra só com consentimento explícito.

**Entregas**
- Flag `devil_mode` + HITL obrigatório.
- Allowlist de tools e orçamento próprio (páginas, tempo, taxa).
- Trilha de auditoria completa; cancelamento imediato.

**Aceite**
- Sem flag, nenhum caminho do Diabo executa probe extra.
- Com flag, tudo é rastreável.

---

## Fase M6 — Probes de comportamento (o salto de “poder”)

**Meta:** passar de “há um form em /sqli” para “há comportamento anômalo **reproduzível** sob política”, ainda sem virar exploit kit.

**Status (set/2026):** **M6 P0 + P1 + P2 + P3 entregues** — reflexão e erro verboso (P0), injeção por replay controlado + upload por observação de form (P1), CSRF (POST de estado sem token) + redirect aberto reproduzível (P2) e authn fraca com resposta diferencial (P3) sob política versada (`backend/policies/probes/reflection_p0.yaml`, `verbose_error_p0.yaml`, `injection_p1.yaml`, `upload_p1.yaml`, `csrf_p2.yaml`, `redirect_p2.yaml`, `authn_p3.yaml`), sem payload de ataque, com os guardrails da 6.3, allowlist de classes por run (`probe_classes`) e gate por profundidade (probes só em `deep`). O P2 de redirect conta com observação de redirect 3xx no scan (a URL original fica em `requested_url` no mapa de rotas, para o probe re-consultar a rota de origem). O P3 de authn é o primeiro sinal ativo: um diferencial mínimo de login (2 envios com a MESMA senha sentinela e usuários controlados — nunca credenciais reais, nunca brute force) para detectar enumeração de usuário. Findings na seção **Comportamento** do relatório e auditoria “qual regra gerou este finding?”. M7–M10 seguem no escopo.

### 6.1 Ideia central

Para cada **classe de risco**, definir:

1. **Pré-condição** — lead observacional (form, parâmetro, rota).
2. **Probe permitido** — ações mínimas, rate-limited, no escopo.
3. **Sinal positivo** — o que na resposta caracteriza lead forte (não “PoC de CTF”).
4. **Sinal negativo / FP** — o que descarta.
5. **Severidade candidata** e se exige HITL.

Probes são **políticas versionadas** (YAML/JSON), não prompts soltos do LLM inventando ataque.

### 6.2 Classes prioritárias (ordem sugerida)

| Prioridade | Classe (alto nível) | Entrada típica no Argus | Tipo de sinal (conceitual) |
|------------|---------------------|-------------------------|----------------------------|
| P0 | Reflexão / saída não codificada | parâmetro refletido | eco perigoso em contexto observável |
| P0 | Erro verboso / info leak | body com stack/SQL/path | detalhe interno estável no re-probe |
| P1 | Injeção em entrada de dados | forms/params de lab e app real | diferença de comportamento sob entrada controlada pela política |
| P1 | Upload | form `file` | aceitação de tipo/tamanho fora do esperado (só observação de resposta) |
| P2 | CSRF / estado de sessão | forms de mudança de estado | ausência de token / comportamento de estado |
| P2 | Redirect aberto | params de URL | redirect para destino externo observado |
| P3 | Authn fraca | login | mensagens/enumeração/resposta diferencial (sem brute force agressivo) |

> Detalhes de *como* montar cada probe ficam na implementação interna e na política — este roadmap **não** documenta payloads nem playbooks de exploração.

### 6.3 Guardrails obrigatórios da M6

- Allowlist de classes por composição / cliente.
- Teto de probes por run e por endpoint.
- Proibição de destruição de dados, spam e ações fora do escopo.
- Todo probe gera evidência estruturada (request resumido, response resumido, regra da política que disparou).
- LLM **não** inventa probe: só escolhe entre políticas já aprovadas (Imperador/Carro).

### 6.4 Aceite M6

- Em lab autorizado (DVWA), o relatório ganha seção **Comportamento** com itens derivados de política, não só do crawl.
- Em alvo real, default é classes P0 apenas até o operador liberar P1+.
- Auditoria permite responder: “qual regra gerou este finding?”.

---

## Fase M7 — Sessão, papéis e fluxos

**Meta:** avaliar com contexto de usuário, não só anônimo.

**Entregas**
- Múltiplos perfis de sessão (anônimo, user, admin) via config autorizada.
- Crawl e probes por papel.
- Detecção de **diferença de acesso** entre papéis (lead de controle de acesso), sem enumeração agressiva.
- Fluxos multi-step gravados como “jornadas” (login → ação → efeito observado).

**Aceite**
- Relatório indica “visível só em sessão X”.
- Sem credenciais configuradas, M7 degrada com graça para anônimo.

### M7-P0 (entregue)
- **Sessão única com consciência de sessão** (fatia rasa): o relatório passa a saber *em qual canal* cada página foi observada.
- `TargetPage.session` etiqueta cada página (`user` quando o login dinâmico foi aplicado, `anon` caso contrário).
- `ScanReport.sessions` carrega metadados da sessão observada (nome, `auth_status`, cookies, contagem); `auth_status`/`auth_cookies` legados continuam.
- **Baseline anônimo**: após login bem-sucedido, UM GET anônimo por URL base (client novo, jar vazio) re-observa a home sem a sessão — custo mínimo, sem segundo crawl.
- **Finding** "Conteúdo visível apenas em sessão autenticada (controle de acesso)" (categoria `Aplicação / controle de acesso`, `candidate`, `confidence=0.4`): dispara só quando a URL base é alcançada pela sessão `user` mas o baseline anônimo não a alcança (status não-2xx ou redirect para fora da base, ex. → `/login`). Nada é enumerado.
- **Degradação graciosa**: sem credenciais → crawl anônimo (sessão `anon`), nenhum request extra; login falho degrada para anônimo com `auth_status` no relatório.
- Route map etiqueta cada rota com a sessão (`extras.routes[].session`); export summary inclui `sessions`.
- **Próximas fatias**: M7-P2 = probes por papel (entregue) + jornadas multi-step (P3).

### M7-P1 (entregue)
- **Múltiplos perfis de sessão** (`SCAN_SESSION_PROFILES`, JSON list de `{name, login_url, username, password}`): substitui o `SCAN_LOGIN_*` único quando definido.
- **Clients isolados**: o primeiro perfil reutiliza o client compartilhado do run (verifier/probes M6 seguem autenticados na sessão primária); cada perfil extra ganha client fresco com jar próprio. Injeta `client_factory` para testes compartilharem a semântica de rate limit.
- **Crawl por papel**: cada perfil crawlea a base com seu próprio jar; `TargetPage.session` recebe o nome do perfil; órfão/login falho degrada (sessão com `auth_status` e excluída das comparações).
- **Finding "Acesso distinto entre sessões (controle de acesso)"**: para rotas observadas sob ≥2 sessões, quando uma aparece em um papel e não em outro (`extras.routes[]` com `accessible_in`/`not_in`). Anon-blind (P0) generalizado para qualquer perfil com baseline anônimo.
- Custo: requisições ≈ nº de perfis × orçamento do crawl; rate limit global por host mantido.

### M7-P2 (entregue)
- **Probes por papel**: o `ProbeEngine` (M6) reprova cada lead com o **client da sessão que o observou** — `session_clients` (injetado via `run(session_clients=...)`), com fallback para o client default do run quando a sessão do lead não tem client próprio (ex. `anon`).
- **Leads conscientes de sessão**: `_Lead.session`; dedupe de lead por `url|param|session` — a MESMA URL observada em papéis distintos gera um probe por papel, dentro do mesmo teto `max_probes`/`max_per_endpoint` global.
- **Rastreabilidade**: cada registro de probe carrega `session`; o finding "Comportamento / ..." expõe `extras.sessions` (quais papéis reproduziram o sinal).
- **Pipeline de sessão por lead**: rota do route map e vetores de entrada carregam `session`; reflexões e erros verbosos repetidos sob outra sessão **mesclam** a sessão no finding agregado (`sessions`), gerando lead por papel sem duplicar findings.
- **Wiring no Chariot**: `_behavior_probes` puxa `scan_service.session_clients()` (keep-alive das jars em memória, nunca serializadas) e repassa ao engine; degrada para registro se qualquer passo falhar.

### M7-P3 (entregue)
- **Jornadas multi-step**: catálogo versionado `policies/journeys/*.yaml` — fluxos que o operador escreve (ex.: "área administrativa": abrir painel → listar recursos) como passos (método + path + body literal estático + efeito esperado `status_in`/`contains`). O Argus **não inventa passo**: só re-executa o que foi versionado.
- **Re-execução por papel**: cada jornada roda idêntica para anônimo (client fresco, quando `run_anonymous`) e para cada sessão autenticada do `session_clients` do scan — resultados comparados passo a passo.
- **Finding "Comportamento / Jornada / ..."**: quando o mesmo passo alcança o efeito esperado em um papel e não em outro, gera finding `candidate`/HITL com `extras.journey` (id/versão/sha256), `extras.divergent_steps` (`sessions_cs`/`sessions_failed`) e `extras.sessions`. Trilha de auditoria por passo (`session`, status, `effect_ok`, `skip_reason`).
- **Guardrails idênticos aos probes M6**: kill-switch, `ALLOWED_SCOPES`, robots, rate-limit do `ScanHTTPClient`, teto `JOURNEY_MAX_STEPS_PER_SESSION`; allowlist por prioridade (`journey_classes_default=p0` → só jornadas P0). Só rodam em `depth=deep`, junto aos probes.
- **Wiring no Chariot**: `_journeys` usa `state.journey_engine` (ou `build_journey_engine()`) e repassa `session_clients`; findings ganham id `F-...`; degrada para registro. Exemplos: `admin_area_p0` (P0, painel → recursos) e `account_self_p1` (P1, perfil → recurso privado).
- **Próximas fatias**: M7-P3 = jornadas multi-step (login → ação → efeito observado, gravadas como fluxos e re-executadas por papel).

---

## Fase M8 — APIs e superfícies modernas

**Meta:** não ficar preso só a HTML de form.

**Checklist M8-P0 (ingestão de OpenAPI/Swagger): entregue.**
- `ScanService._discover_openapi`: candidatos `openapi.json`/`swagger.json`/
  `openapi.yaml` (1 GET por candidato, primeiro que validar vence), com o client
  da sessão do crawl; robots por path; fail-closed (spec inválida/sem paths/
  host divergente → nota, sem superfície); teto de bytes/rate-limit/timeout do
  client; ctrl `SCAN_OPENAPI_ENABLED` (ligado via `build_scan_service`).
- `ScanReport.api_spec` (`url`/`sha256`/`session`) + `api_endpoints`
  (`method`/`path`/`params`/`session`); `to_dict` cobre ambos.
- Finding agregado "endpoints de API mapeados (OpenAPI)" em `Aplicação /
  superfície de API`, `candidate`, com `extras.endpoints[]` prontos para servir
  de leads aos probes JSON do M8-P1; breakdown/sumário `api_endpoints`.
- Suíte `tests/test_openapi_m8.py` (7).

**Checklist M8-P1 (probes de política adaptados a JSON): entregue.**
- `_Lead` novo: cada endpoint da superfície (`report.api_endpoints`) vira lead
  (`lead_kind: api`), URL resolvida, apenas nomes de parâmetros (nunca valores
  inventados); re-prova GET bare e só-observa.
- Sinais JSON-adaptados (`SignalRule`): `json_response`, `json_has_array`,
  `json_contains` (procura em chaves/valores do JSON parseado, não substring
  cru). Mesmos guardrails M6 (escopo/kill-switch/robots/rate-limit/
  per-endpoint/probe cap) e players por sessão (M7-P2).
- Políticas: `api_json_error_p0.yaml` (P0, default) e `api_bulk_p1.yaml` (P1,
  allowlist) — findings "Comportamento / ...".
- Suíte `tests/test_probing_m8.py` (13).

**Entregas**
- Ingestão de OpenAPI/Swagger quando disponível.
- Mapeamento de endpoints, métodos e parâmetros.
- Probes de política adaptados a JSON (mesmos guardrails da M6).
- GraphQL: introspecção **só se autorizada** e política específica.
- Fingerprint de WebSocket (detecção de upgrade), testes profundos depois.

**Aceite**
- Alvo com OpenAPI gera superfície de API no relatório.
- Sem especificação, fallback para links e calls observados no crawl.

---

## Fase M9 — Qualidade, baseline e escala

**Meta:** poder operacional de verdade.

**Entregas**
- Baseline por alvo: diff de findings entre runs.
- Deduplicação global e fingerprint de finding.
- Filas / isolamento para N alvos (ainda com limites de concorrência).
- Modo CI: exit code, SARIF, gate em PR (só findings acima de limiar).
- Métricas: taxa de FP reportada pelo operador, tempo até primeiro lead útil, custo/tokens por finding útil.

**Aceite**
- Segundo run no mesmo alvo destaca *novos* e *resolvidos*.
- CI consome SARIF sem intervenção manual.

---

## Fase M10 — Produto e política

**Meta:** o poder é usável por operadores, não só pelo autor do código.

**Entregas**
- Pacotes de política: `lab`, `bugbounty-web`, `api-only`, `surface-only`.
- UI: escolher depth, classes M6 liberadas, perfis de sessão, HITL.
- Relatório executivo vs técnico.
- Trilha de autorização (nota de escopo ligada ao Target/Run).
- Presets Tarot: composições prontas (recon, app-map, deep-web, api).

**Aceite**
- Operador configura um run poderoso sem editar YAML na mão.
- Política do run exportável e reproduzível.

---

## Arquitetura alvo (visão)

```text
                    ┌─────────────────────────┐
                    │   Política do run       │
                    │ depth, classes, papéis  │
                    └───────────┬─────────────┘
                                │
┌──────────────┐   ┌────────────▼────────────┐   ┌──────────────┐
│   Sources    │   │   Grafo de arquétipos   │   │    Tools     │
│ OSINT / CVE  │──▶│ Imperador → … → Justiça │◀──│ HTTP/sessão  │
└──────────────┘   │         ↓               │   │ políticas M6 │
                   │   Scan + Probes         │   └──────────────┘
                   └────────────┬────────────┘
                                │
                   ┌────────────▼────────────┐
                   │  Findings + evidência  │
                   │  candidate → validated  │
                   └────────────┬────────────┘
                                │
                   ┌────────────▼────────────┐
                   │ Relatório / SARIF / UI  │
                   └─────────────────────────┘
```

---

## O que torna o Argus “poderoso” (checklist de produto)

- [ ] Mapa de app confiável (já quase: M1)
- [ ] Re-probe ao vivo (M2)
- [ ] Profundidade explícita (M3)
- [ ] Validação conservadora (M4)
- [ ] Modo agressivo auditável (M5)
- [x] Comportamento sob política (M6) — **P0..P3 entregues** (reflexão, erro verboso, injeção replay, upload, CSRF, redirect aberto, authn diferencial) ← **principal salto de poder**
- [ ] Contexto de sessão/papéis (M7) — **P0+P1+P2+P3 entregues** (sessão única "visível só autenticado" + múltiplos perfis com "acesso distinto entre sessões" + probes por papel + jornadas multi-step por sessão)
- [ ] API/GraphQL (M8)
- [ ] Diff/CI/escala (M9)
- [ ] Pacotes e UX de política (M10)

Sem M6, o Argus é um **excelente mapeador e priorizador**.  
Com M6–M8, vira **plataforma poderosa de avaliação**.  
Com M9–M10, vira **produto operável em time**.

---

## Ordem realista de entrega

| Horizonte | Fases | Resultado para o usuário |
|-----------|-------|---------------------------|
| Agora | M1b + M2 | Relatório limpo + leads revalidados |
| +1 ciclo | M3 + M4 | Depth e confiança profissionais |
| +1 ciclo | M5 | Stress opt-in |
| Feito | M6 P0+ → P3 | Seção Comportamento: reflexão, erro verboso, injeção replay, upload, CSRF, redirect aberto, authn diferencial |
| +2 ciclos | M7 | Authz/sessão (P0: sessão única + "visível só autenticado"; P1: múltiplos perfis + "acesso distinto entre sessões" — entregues) |
| Depois | M8–M10 | API, escala, produto |

---

## Riscos e limites conscientes

| Risco | Mitigação |
|-------|-----------|
| Expectativa de “scanner que explora tudo” | Comunicação de produto: leads + comportamento sob política |
| Probe excessivo em alvos reais | Default P0; P1+ opt-in; rate limits; depth |
| FP em massa na M6 | Políticas versionadas + Justiça + feedback do operador |
| LLM inventando ataque | Probes só de catálogo aprovado |
| Escopo jurídico | Nota de autorização por Target; kill-switch; logs |

---

## Métricas de sucesso (produto poderoso)

1. **Tempo até primeiro lead útil** de aplicação (menor é melhor).
2. **% de findings que o operador marca como úteis** (meta a calibrar).
3. **% validated que se sustentam em revisão humana**.
4. **Custo (tokens/API) por finding útil**.
5. **Cobertura:** rotas vistas / rotas de interesse (quando houver sitemap/OpenAPI).
6. **Diff limpo** entre runs sem mudança real no alvo (estabilidade).

---

## Relação com documentos anteriores

| Documento | Papel |
|-----------|--------|
| `PLANO_MELHORIA_ARGUS.md` | M1–M5 originais |
| `SUGESTOES_AJUSTE_POS_RUN7.md` | M1b + checklist M2 tático |
| **Este (`ROADMAP_ARGUS_PODEROSO.md`)** | Horizonte de poder (M6–M10) + critérios de produto |

---

## Próxima ação recomendada

1. Fechar **M1b + M2** (já especificados).  
2. Implementar **M3 + M4** para profissionalizar depth e validação.  
3. ~~Abrir design formal da **M6 P0→P3**~~ — **P0+P1 entregues** (reflexão, erro verboso, injeção replay controlado, upload por observação), **P2 entregue** (CSRF de estado sem token + redirect aberto reproduzível com observação de redirect 3xx no scan) e **P3 entregue** (authn fraca: login com resposta diferencial e controles sentinela, sem brute force), sempre dentro dos guardrails da 6.3. Próximo: design formal da **M7** (sessão/papéis).  
4. Só então expandir M7–M8.

Este é o caminho para o Argus ser **poderoso de verdade**: não por quantidade de findings, e sim por **mapa + comportamento reproduzível + política + confiança calibrada**.
