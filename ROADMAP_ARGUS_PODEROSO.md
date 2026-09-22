# Roadmap — Argus Engine Poderoso

**Objetivo:** transformar o Argus de orquestrador com recon + mapa de aplicação em uma **plataforma poderosa de avaliação autorizada** — densa em sinal, baixa em ruído, auditável e segura de operar.

**Não-objetivo:** virar exploit framework autônomo ou substituir pentest humano sem evidência e sem escopo.

**Estado de partida (set/2026)**
- M1 validado no DVWA (run #7): superfície, config, forms, rotas, reflexão, erros verbosos, relatório por seções.
- Próximo imediato: polish de relatório + M2 (tools HTTP/sessão + re-probe do Carro).
- M3–M5 do plano anterior continuam válidos; este documento **estende** o horizonte.
- **M6 P0 entregue (set/2026):** proactive probes de comportamento sob política no run (ver seção M6).
- **M6 P1 entregue (set/2026):** injeção (replay controlado) + upload (observação de form), com allowlist de classes por run.

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
[Poder]        M6  Probes de comportamento por classe (controlados) — P0+P1 pronto, P2+ pendente
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
| `deep` | Auth + crawl amplo + forms/rotas + re-probe Carro + probes M6 (P0 default; P1+ via allowlist `probe_classes`) |
| `deep+` (futuro, após P2) | Inclui classes P2/P3 dentro da política |

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

**Status (set/2026):** **M6 P0 + P1 entregues** — reflexão e erro verboso (P0) e injeção por replay controlado + upload por observação de form (P1) sob política versada (`backend/policies/probes/reflection_p0.yaml`, `verbose_error_p0.yaml`, `injection_p1.yaml`, `upload_p1.yaml`), sem payload, com os guardrails da 6.3, allowlist de classes por run (`probe_classes`) e gate por profundidade (probes só em `deep`). Findings na seção **Comportamento** do relatório e auditoria “qual regra gerou este finding?”. P2–P3 da tabela 6.2 seguem pendentes.

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

---

## Fase M8 — APIs e superfícies modernas

**Meta:** não ficar preso só a HTML de form.

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
- [x] Comportamento sob política (M6) — **P0+P1 entregues** (reflexão, erro verboso, injeção replay, upload); P2–P3 pendentes ← **principal salto de poder**
- [ ] Contexto de sessão/papéis (M7)
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
| Feito | M6 P0 + P1 | Seção Comportamento: reflexão, erro verboso, injeção replay, upload |
| +2 ciclos | M6 (P2→P3) | CSRF, redirect, authn fraca |
| +2 ciclos | M7 | Authz/sessão |
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
3. ~~Abrir design formal da **M6 P0/P1**~~ — **P0+P1 entregues** (reflexão, erro verboso, injeção replay controlado, upload por observação). Próximo: design formal da **M6 P2** (CSRF + redirect aberto), ainda dentro dos guardrails da 6.3.  
4. Só então expandir P3 e M7–M8.

Este é o caminho para o Argus ser **poderoso de verdade**: não por quantidade de findings, e sim por **mapa + comportamento reproduzível + política + confiança calibrada**.
