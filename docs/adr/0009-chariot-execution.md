# ADR-0009 — Execução real não destrutiva no modo normal (Carro, Etapa 15)

**Status:** Aceito

## Contexto

O Carro é o arquétipo de execução. Até a Etapa 15, seu modo normal era
**puramente passivo** (`action: "safety"`): observava sinais já coletados
(scan ativo, fontes, correlação CVE) e marcava candidatos
(`requires_human_review=True`) sem tocar no alvo; no Modo Diabo, após
aprovação HITL, registrava honestamente `no_backend` — não havia backend de
execução real algum. O Modo Diabo continua deliberadamente sem backend (decisão
de produto registrada na Etapa 2 do ROADMAP e em `SECURITY.md`: evoluí-lo para
exploits depende de estar atrás da camada Diabo completa — sandbox + HITL +
auditoria).

Havia, porém, uma fronteira segura e valiosa dentro do **modo normal**: o
Argus já faz scanner ativo autorizado (ADR-0006) com controles de escopo,
kill-switch, robots, rate limit e timeout; e já executa **tools do operador**
através do `ToolExecutor` da Etapa 5, com gating de `destructive`. O Carro em
modo normal poderia:

- **re-provar ao vivo** os candidatos vindos do scan, anexando evidência
  presencial (confirma ou refuta);
- **invocar as tools NÃO destrutivas** registradas pelo operador
  (`TOOLS_MANIFEST`) uma vez cada, contando como execução real auditável.

Sem isso, todo run normal é enteramente simulado ("simulate") — correto por
definição, mas pouco útil para confirmar leads.

## Decisão

**Modo normal do Carro ganha uma camada de execução real NÃO destrutiva.**

### 1. Verificação ao vivo (`VerificationService`, `app/scanning/verify.py`)

- Re-prova o `probe_url` de cada achado candidato com uma **GET simples** sob
  os mesmos controles do scanner ativo (escopo, kill-switch, robots por host,
  rate limit, timeout, headers de auditoria) via `ScanHTTPClient`.
- Para cada resposta fresca re-roda `detect_on_page`: se o título do achado
  reaparece → **confirmado** (`verification.confirmed=true`); se não →
  **não reprovado** (`confirmed=false`); se a sondagem foi bloqueada
  (kill-switch, fora de escopo, robots disallow, host fora do ar) →
  **pulada** com `skip_reason` — **jamais fabrica resultado**.
- HTTPS fora do ar → fallback documentado para HTTP (mesma política do scan).
- Limitada por `CHARIOT_VERIFY_MAX_PROBES` (default 10) e desligável por
  `CHARIOT_VERIFY_ENABLED`. Acha sem URL sondável (sem `probe_url`/`affected`)
  fica `verification: null` (não verificado).
- O resultado é anexado ao achado via `Finding.meta` (campo
  `verification`) e exposto em `finding_report`/export — sem migração (fluxo
  `meta` já existente).

### 2. Tools do operador (via `build_tool_executor`, `app/tools/executor.py`)

- O Carro invoca **uma vez** cada tool registrada no `TOOLS_MANIFEST` cujo
  `destructive=false`. Tools destrutivas NUNCA rodam em modo normal — o gating
  da Etapa 5 é a fronteira real.
- Falha de uma tool degrada para `outcome: "failed"` no histórico; verificação
  ao vivo continua valendo. Nenhuma falha derruba o run.
- Sem manifest (ou registro vazio) o Carro degrada para as sondas embutidas.

### 3. Registro da execução no histórico

- O `ChariotOutput` continua com `action: "safety"` (papel do nó em modo
  normal), mas `mode` passa a `"live"` quando houve execução real
  (`verified`/`refuted`/`tools_tried` presentes; `"tool_runs"` detalha cada
  invocação com outcome durável/falha). Sem execução, `mode: "simulate"` como
  antes. O literal `execute` permanece reservado ao caminho do Modo Diabo.

### 4. Injeção dos serviços

`VerificationService` e `ToolExecutor` entram no run por composição injetável
(`Director.__init__`/`provision`, `state.set_verification_service`/
`set_tool_executor`, `execute_run`) — lembrete de arquitetura: `Director.run`
reconstrói o `GraphState` via `model_dump()` (que **descarta** `PrivateAttr`),
então os serviços precisam ser passados ao `Director` em cada ponto de
criação, não apenas setados no estado. Modo offline/determinístico (testes,
sem serviços) continua produzindo `mode: "simulate"`.

## Consequências

- **Positivas:** runs normais deixam de ser totalmente simulados; leads do scan
  ganham confirmação/refutação ao vivo com evidência; as tools não destrutivas
  do operador finalmente têm um consumidor automático; tudo permanece auditável
  no histórico e nos exports.
- **Negativas/limites (deliberados):** o Modo Diabo continua **sem** backend de
  execução real — evoluí-lo para exploits segue adiado; sondas/tools só rodam se
  o alvo estiver em `ALLOWED_SCOPES` (sem escopo validado não há execução, nem
  mesmo verificação); a cap de probes e o robots podem deixar um candidato sem
  verificação — nunca como falso positivo.

## Testes

- `tests/test_chariot_execution.py`: sonda confirmando (achado ainda presente na
  resposta fresca), refutando (página "consertada"), pulando por robots, teto de
  probes, alvo fora de escopo, `enabled=false`, fallback HTTP e achado sem URL;
  Camada live do Carro (probes + tools), tool destrutiva nunca invocada, falha de
  tool e de verifier degradando o run, e modo `simulate` sem serviços injetados.