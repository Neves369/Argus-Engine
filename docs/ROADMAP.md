# ROADMAP — Argus Engine

Plano vivo de implementação da plataforma de **pentest e bug bounty autorizada** com
scanning ativo e orquestração de agentes. Este documento é a fonte de verdade das
etapas, com o estado atual do repositório e o que falta em cada fase.

> **Uso autorizado apenas.** Este projeto só deve ser usado em alvos com autorização
> explícita e escopo definido, em conformidade com leis locais e políticas de bug bounty.

---

## Princípios inegociáveis (repetir em toda etapa)

1. Uso exclusivo em alvos com autorização explícita e escopo definido.
2. **Relatar ≠ ensinar**: o relatório de segurança pode conter classe (CWE/OWASP), severidade (CVSS), CVE IDs, referência a exploit público e remediação; o que segue proibido é detalhar/ensinar a técnica ofensiva em si (payloads, chaining, passo-a-passo de exploração).
3. Controles de segurança operacional, logging completo e kill-switch desde o dia 1.
4. Modelos abliterados apenas atrás de policy gateway + sandbox + human-in-the-loop em ações sensíveis.
5. Economia de tokens e observabilidade desde o início.
6. **Scanning ativo** (download de página, crawl, análise de headers/forms, detecção de vulnerabilidades OWASP Top 10) roda **sempre** quando o alvo está em `ALLOWED_SCOPES` — não depende do Modo Diabo. **Modo Diabo** (execução destrutiva/invasiva, futuramente exploits) é uma camada separada que exige escopo validado + sandbox + kill-switch + auditoria + HITL.

---

## Scanning Ativo vs Modo Diabo

Estas são duas funcionalidades **separadas**:

| Funcionalidade | Quando roda | O que faz | Controles |
|---|---|---|---|
| **Scanning Ativo** (padrão) | **Sempre** quando alvo em `ALLOWED_SCOPES` | Download de página, crawl, análise de headers/forms, fingerprinting, detecção de vulnerabilidades OWASP Top 10 | Rate limiting, timeout, self-imposed restrictions, logging completo |
| **Modo Diabo** (futuro) | Só com `DEVIL_MODE=ON` | Execução de scripts invasivos/destrutivos (exploits) | Escopo validado + sandbox + kill-switch + auditoria + HITL |

**Scanning ativo NÃO é Modo Diabo.** O scanning é funcionalidade core — ele访访 o alvo para encontrar vulnerabilidades reais. O Modo Diabo é uma camada adicional para execução sem restrições.

---

## Decisões de stack (já definidas)

### Backend
| Camada | Tecnologia | Status |
|---|---|---|
| Linguagem | Python 3.11+ (ambiente atual: 3.13) | Definida |
| Framework API | FastAPI + Uvicorn | Implementada |
| Orquestração | LangGraph (grafo de agentes com estado tipado) | Implementada |
| Persistência | SQLite + SQLAlchemy 2.0 (async) | Implementada |
| Estado do grafo | Pydantic `BaseModel` | Implementado |
| Config | `.env` + pydantic-settings | Implementada |
| Logging | Estruturado (JSON) | Implementado |
| Sandbox | Docker | Implementado (Etapa 5) |
| Modo Diabo | flag `DEVIL_MODE` + HITL em ações destrutivas | Implementado (gating; execução de exploits: futura) |
| CLI | Typer/Rich | Implementada (Etapa 8) |

### Frontend
| Camada | Tecnologia | Status |
|---|---|---|
| Framework | Vite + React 19 | Implementado |
| Canvas de grafo | `@xyflow/react` (React Flow) | Implementado (canvas funcional, Etapa 8) |
| Animações | Framer Motion + Rive | Implementado (parcial — Framer Motion: painel/toast; Rive: adiado) |
| Estado | Zustand | Implementado (store de UI em `frontend/src/store/ui.ts`) |
| Estilo | Tailwind + shadcn/ui | Implementado (parcial — Tailwind v4 com preflight off; shadcn/ui: adiado) |

### Arquétipos Tarot (Etapa 2)
Seis arquétipos: Orquestrador/Diretor = **O Imperador (IV)** · O Eremita (IX) · O Louco (0) ·
A Justiça (XI) · O Carro (VII) · O Mago (I). O **Diabo (XV)** virou o **Modo Diabo**
(modo de execução — ver acima). Alvo representado por **A Torre (XVI)**.

---

## Visão geral das etapas

| Etapa | Nome | Objetivo principal | Status |
|---|---|---|---|
| 0 | Fundação e Governança | Repositório, princípios, políticas | ✅ Concluída |
| 1 | Núcleo de Orquestração | Grafo de agentes com estado tipado | ✅ Concluída |
| 2 | Arquétipos e Personas | Agentes reutilizáveis (Tarot) | ✅ Concluída |
| 3 | Roteador de LLMs | Gateway multi-provider (OmniRoute-like) | ✅ Concluída |
| 4 | Persistência e Evidências | SQLite completo + evidências | ✅ Concluída |
| 5 | Tool Registry e Sandbox | Ferramentas com permissão e isolamento | ✅ Concluída |
| 6 | Filtro de Qualidade | Anti-falso-positivo | ✅ Concluída |
| 7 | Economia de Tokens | RTK + Caveman | ✅ Concluída |
| 8 | Interface e Composição Visual | Canvas de arquétipos | ✅ Concluído |
| 9 | Integrações Externas | Fontes de dados cacheadas | ✅ Concluído |
| 10 | Observabilidade, HITL e Hardening | Produção auditável e segura | ✅ Concluída |
| 11 | Relatório de Segurança | Achados com substância (severidade/CVE/exploit/remediação) | ✅ Concluída |
| 12 | Scanning Ativo (OWASP Top 10) | Download de página, crawl, análise de headers/forms, detecção de vulnerabilidades | ✅ Concluída |
| 13 | Integração de Ferramentas Reais | NVD/CISA KEV/CVE.report no pipeline, extractors de OSINT, tools reais | ✅ Concluída |

---

## Etapa 0 — Fundação e Governança

**Status:** `[x]` Concluída

**Objetivo:** criar a base do projeto, políticas e estrutura que todo o resto respeitará.

**Entregáveis**
- [x] Repositório Git com estrutura de pastas (`backend/`, `frontend/`)
- [x] `README.md` (back-end) — documentação de setup e execução
- [x] `.env.example` + gestão de segredos (sem segredo commitado)
- [x] Configuração base (`pyproject.toml`, pydantic-settings)
- [x] Logging estruturado (`app/core/logging.py`)
- [x] Política de escopo + kill-switch (`app/core/security.py`)
- [x] Testes básicos (health, targets, grafo)
- [x] `CONTRIBUTING.md`, `SECURITY.md`, `LICENSE`, `AGENTS.md`
- [x] Documento de Política de Uso Autorizado versionado e carregado no runtime (`backend/policies/authorized-use.md` + `GET /policy`)
- [x] CI básico (lint, type-check, testes) — `.github/workflows/ci.yml`

**Observações / pendências**
- `make setup` documentado no `Makefile` (Linux) e comandos Windows no `README`.
- ADRs (`docs/adr/`) ainda não iniciados.

---

## Etapa 1 — Núcleo de Orquestração (Grafo de Agentes)

**Status:** `[x]` Concluída

**Objetivo:** ter um orquestrador que monta e executa grafos de agentes com estado compartilhado tipado.

**Entregáveis**
- [x] Estado compartilhado tipado (`app/orchestration/state.py` — `GraphState` Pydantic)
- [x] Implementação base com LangGraph (`app/orchestration/graph.py`)
- [x] Orquestrador principal ("Director") (`app/orchestration/director.py`)
- [x] Arestas condicionais (confiança, orçamento, kill-switch)
- [x] Mecanismo de stop conditions e orçamento (`should_continue`)
- [x] Interface mínima do orquestrador (`run`, `pause`, `resume`, `inject_human_input`)
- [x] `devil_mode` no `GraphState` + desvio condicional simular (OFF) vs executar (ON)
- [x] Execução paralela básica — pernas independentes de um nó (gateway LLM + coleta de
      fontes + scan ativo) rodam em concorrência via `asyncio.gather`, preservando ordem
      e estado (`AGENT_PARALLEL`, default on; desligar => sequencial). Cobertura:
      `tests/test_execution_parallelism.py` (sobreposição de wall-clock + semântica).

**Critérios de aceite**
- [x] É possível definir um grafo de 3 nós, executar e receber estado final tipado.
- [x] Logs estruturados de cada transição de nó (via `history` no estado).

**Observações / pendências**
- Paralelismo de nós em DAG (fan-out: vários nós após um diretor) ainda não existe — os grafos
  atuais são cadeias lineares; o paralelismo entregue é o intra-nó (pernas de I/O independentes).
- Persistência/retomada de runs usa JSON no estado (retomada real ainda pendente).

---

## Etapa 2 — Arquétipos e Personas

**Status:** `[x]` Concluída (dentro do escopo mantido — ver nota sobre Modo Diabo)

**Objetivo:** transformar agentes em arquétipos reutilizáveis e composáveis.

**Entregáveis**
- [x] Definição formal de Arquétipo (`app/agents/base.py` — `BaseArchetype`)
- [x] Registry de arquétipos (`app/agents/__init__.py` — `get_archetype`)
- [x] 3 arquétipos mínimos (Imperador/Diretor, Eremita/Coletor, Justiça/Analista)
- [x] Biblioteca completa de 6 arquétipos Tarot (Imperador, Eremita, Louco, Justiça, Carro, Mago)
- [x] Mecanismo de composição (lista ordenada de arquétipos → grafo dinâmico)
- [x] Validação de compatibilidade entre arquétipos (básica: sem duplicatas, termina em `justice`)
- [x] System prompts completos por persona (`system_prompt()` próprio em cada arquétipo, `app/agents/builtin.py`)
- [x] Schema de saída obrigatório por arquétipo (JSON Schema) — `app/agents/schemas.py` +
      `BaseArchetype.validate_entry()`/`output_json_schema()`; exposto via
      `GET /archetypes` e `GET /archetypes/{key}/schema`
- [~] ~~Modo Diabo como perfil de execução~~ — **fora de escopo por decisão do operador**
      (ver nota abaixo)

**Critérios de aceite**
- [x] Um usuário consegue montar um grafo só com arquétipos e executá-lo (via API, com os 3 mínimos).
- [x] Cada arquétipo declara explicitamente suas tools e limites (`allowed_tools`).
- [x] Montar e executar grafo com os 6 arquétipos.
- [x] Cada arquétipo tem um system prompt específico e um `output_schema` que sua
      entrada de histórico é obrigada a satisfazer (validado em toda execução, não
      só documentado).

**Nota — Modo Diabo descontinuado**
- Decisão do operador: a plataforma não vai evoluir o "Modo Diabo" para plugar
  modelos abliterados/sem restrição nem ferramentas de execução realmente
  destrutivas. O toggle `devil_mode` e o gating condicional (`ChariotAgent`,
  `ToolExecutor`) permanecem no código como estão hoje — infraestrutura de
  roteamento inofensiva, sem modelo abliterado nem ferramenta destrutiva real
  plugada — mas não serão estendidos além disso.
- Os pontos "5" (raciocínio vs execução abliterada) e a exposição de HITL para
  ligar o Modo Diabo, listados abaixo em "Pontos a discutir", ficam
  descontinuados junto.

**Pontos a discutir**
1. Lista final de arquétipos e responsabilidades — ✅ fechada (6 arquétipos acima).
2. ~~Separação entre "raciocínio" (modelos fortes) e "execução controlada"
   (menores/abliterados)~~ — descontinuado (ver nota acima).
3. Como o orquestrador escolhe combinações automaticamente — ainda em aberto,
   sem prioridade definida.
4. Nível de customização do usuário vs hardcoded de segurança — ainda em aberto.

---

## Etapa 3 — Roteador de LLMs (estilo OmniRoute)

**Status:** `[x]` Concluída (Gemini integrado — ver entregáveis)

**Objetivo:** gateway unificado OpenAI-compatible com múltiplos providers, combos e fallback.

**Entregáveis**
- [x] Cliente unificado
- [x] Suporte a Groq, OpenRouter, OpenAI (OpenAI-compat) e Google Gemini (endpoint OpenAI-compat `/v1beta/openai`; provider `gemini` via `GEMINI_API_KEY`, modelo `gemini-2.5-flash`)
- [x] Estratégias de combo priority e fallback
- [x] Estratégias de combo cost-optimized e auto (`LLM_STRATEGY` no `.env`; `auto` usa cost-optimized para julgamento e priority para execução)
- [x] Tracking de tokens e custo por chamada
- [x] Headers de decisão (qual modelo/provider foi usado)
- [x] Cache de prefixo e compressão (`app/llm/cache.py`, `app/llm/compress.py`)
- [x] Roteamento por modo: modelos sem restrição p/ execução (Modo Diabo ON) vs modelos fixos p/ julgamento/investigação

**Critérios de aceite**
- [x] Trocar de provider não exige mudança no código dos agentes (agentes chamam o gateway via `LLMRouter`/`attempt_completion`).
- [x] Toda chamada registra tokens, custo e decisão de roteamento.

**Observações / pendências**
- Google Gemini integrado via endpoint OpenAI-compat da Google (`/v1beta/openai`) — igual aos demais providers (sem adapter nativo). Cobertura em `tests/test_gemini_provider.py`.
- `route_for_mode(devil_mode, strategy)` ordena o pool por estratégia: `priority`/`fallback`
  mantêm a ordem declarada em `EXECUTION_MODELS`/`JUDGMENT_MODELS`; `cost-optimized` ordena
  por `price_in + price_out` (mais barato primeiro); `auto` aplica cost-optimized ao pool de
  julgamento e priority ao pool de execução (capacidade importa mais que preço ali). Estratégia
  padrão configurável via `LLM_STRATEGY` (lida em `attempt_completion` quando a chamada não
  especifica uma). Cobertura em `tests/test_llm.py`.
- Cache de prefixo (`app/llm/cache.py`, `PrefixCache`): cache TTL em memória, por
  processo, chaveado em `sha256(provider+model+mensagens+temperature+max_tokens)`.
  `LLMRouter.complete()` consulta antes de cada tentativa de combo e grava depois de
  um sucesso; toda `CompletionResult` traz `decision["cache_hit"]` para observabilidade.
  Configurável via `LLM_CACHE_ENABLED`/`LLM_CACHE_TTL_SECONDS`. É cache de prompt completo
  (não KV-cache de tokens do provider).
- Compressão de prompt (`app/llm/compress.py`): normalização de espaços em branco
  (sempre) + corte de mensagens muito longas mantendo início/fim
  (`LLM_MAX_PROMPT_CHARS`, default 8000 — generoso o bastante pra não afetar os
  contextos curtos atuais dos arquétipos; é uma rede de segurança para prompts
  maiores no futuro, ex. saída de tools ou listas longas de findings).
- Wiring dos 6 arquétipos feito com fallback offline determinístico: sem API key (ou falha de provider) os nós degradam à lógica simulada, mantendo o grafo determinístico/offline nos testes (158 testes verdes). Chariot usa o pool de execução quando Modo Diabo ON; os demais usam o pool de julgamento.

**Pontos a discutir**
1. Do zero vs adaptar OmniRoute ou similar.
2. Mapear "tarefa → combo ideal" (orquestração vs execução vs validação).
3. Tratamento de rate limits e quotas free-tier.
4. Onde aplicar policy gateway antes de modelos abliterados.
5. Como o Modo Diabo altera o pool de modelos disponíveis para execução.

---

## Etapa 4 — Persistência e Evidências (SQLite)

**Status:** `[x]` Concluída

**Objetivo:** tudo que importa fica local, auditável e consultável.

**Entregáveis**
- [x] Models base (`Target`, `Run`) com SQLAlchemy async + SQLite
- [x] Camada de acesso (`app/db/session.py`)
- [x] Schema parcial (`findings`, `evidence`, `decisions`, `agent_runs`, `api_usage`)
- [x] Schema restante (`sessions`, `cve_cache`, `external_data_cache`)
- [x] Migrações (Alembic) — `alembic upgrade head` no startup + `make migrate`
- [x] Armazenamento de evidências (arquivos + metadados + hash SHA-256)
- [x] Exportação de findings (JSON, Markdown)
- [x] Exportação SARIF (`GET /runs/{id}/export?format=sarif`, SARIF 2.1.0)
- [x] Isolamento por run (consultas escopadas por `run_id`/`target_id`)

**Critérios de aceite**
- [x] Um run completo grava e recupera todo o estado (via `Run.result` JSON).
- [x] É possível consultar histórico de um target (listar runs por target_id).
- [x] Findings com estados `candidate → validated → false_positive → discarded`.

**Observações / pendências**
- Nenhuma pendência de schema/migração. `test_migrations.py` garante que os models
  SQLAlchemy e a migration `head` do Alembic nunca divergem (`compare_metadata`),
  então qualquer alteração futura de model exige gerar uma nova revision Alembic
  antes de mesclar (`alembic revision --autogenerate`), ou o teste quebra a CI.

---

## Etapa 5 — Tool Registry e Sandbox

**Status:** `[x]` Concluída

**Objetivo:** expor ferramentas fornecidas pelo operador (CLI, exploits, OSINT, CVE) atrás de um
registry com permissões e isolamento. A plataforma orquestra; as ferramentas e fontes são plugadas via configuração.

**Entregáveis**
- [x] Camada de plugin/config para registrar ferramentas fornecidas pelo operador (manifesto `tools.json` via `TOOLS_MANIFEST`)
- [x] Tool Registry (nome, descrição, kind http/cli, permissões por arquétipo)
- [x] Executor leve (subprocess com timeout / HTTP via httpx)
- [x] Executor com sandbox (Docker preferencialmente)
- [x] Rate limiting e timeouts por tool
- [x] Logging de toda invocação

**Critérios de aceite**
- [x] Um agente só consegue chamar tools explicitamente permitidas no seu arquétipo.
- [x] Toda execução de tool é logada e limitada por tempo/taxa.
- [x] Uma ferramenta CLI/API fornecida pelo operador é registrada via config sem mudar o código do backend.

**Observações / pendências**
- Sandbox Docker (Etapa 5, ver `docs/adr/0007-tool-sandbox.md`): executável
  `kind: cli` roda dentro de um container descartável (`docker run --rm`) com
  `--network=none`, root read-only, `--cap-drop ALL`, `no-new-privileges`,
  limites de pids/CPU/memória e usuário não-root. Opt-in via `TOOL_SANDBOX=true`
  (default desligado, preservando o comportamento anterior). **Fail-closed:**
  com sandbox habilitada e Docker indisponível, a tool NÃO roda — nunca volta
  silenciosamente ao subprocesso sem isolamento. Timeout mata o container
  por nome (`docker rm -f`). Overrides por tool no `ToolSpec`:
  `sandbox_image`, `sandbox_network`, `sandbox_user`.
- Tools `destructive: true` só executam com `devil_mode` ON.

**Pontos a discutir**
1. Formato de declaração das ferramentas fornecidas pelo operador (YAML/JSON/manifesto). — resolvido: manifesto JSON (`tools.json`)
2. Nível de isolamento necessário (Docker, firejail, ou mais leve no início). — resolvido: Docker CLI via subprocess (sem dependência nova)
3. Política de allowlist vs denylist de comandos/ferramentas. — resolvido: allowlist por arquétipo
4. Como o Modo Diabo (ON) libera o acesso a tools destrutivas que ficam bloqueadas no modo OFF. — resolvido: gating por `devil_mode` no executor

---

## Etapa 6 — Filtro de Qualidade (Anti-Falso-Positivo)

**Status:** `[x]` Concluída

**Objetivo:** só findings com evidência e scoring sobem de "candidate" para "validated".

**Entregáveis**
- [x] Pipeline de validação (`app/services/quality.py`)
- [x] Scoring de confiança (regras: confidence + evidências + severidade)
- [x] Validação por regras (scoring + exigência de evidência + blacklist)
- [x] Agente Validador com LLM juiz (usa o gateway da Etapa 3) — `app/services/judge.py`
- [x] Blacklist / local knowledge de falsos positivos conhecidos
- [x] Aprendizado automático de falsos positivos — decisão humana fecha o loop
  (`app/services/fp_rules.py` + tabela `fp_rules`)
- [x] Estados claros no schema (`score`, `requires_human_review`, `validated_at`)
- [x] HITL obrigatório para severidade alta (flag `requires_human_review`)

**Critérios de aceite**
- [x] Nenhum finding chega a "validated" sem passar pelo pipeline (`candidate → validated` só via `/validate`).
- [x] É possível marcar falsos positivos e manter local knowledge (blacklist configurável via `FP_BLACKLIST`).

**Observações / pendências**
- LLM juiz (`LLMJudge`) consulta o gateway (pool de julgamento) em `POST /findings/{id}/validate`, refinando as regras: blacklist, severidade alta e ausência de evidência permanecem proteções inegociáveis que o LLM não sobrescreve (HITL preservado). Sem chave ou falha de provider, degrada ao scoring por regras (offline). Veredito/razão/custo ficam em `Finding.meta["judge"]`.
- **Loop de aprendizagem fechado:** quando o operador marca um finding como
  `false_positive` (`PATCH /findings/{id}`), o sistema extrai uma assinatura
  (título normalizado, mínimo 4 caracteres para não aprender ruído) e a persiste
  em `fp_rules` (`source="learned"`, `source_finding_id`, `hit_count`). Daí em
  diante qualquer candidato similar é suprimido automaticamente no pipeline
  (hard stop, igual à blacklist) e o `validate` incrementa `hit_count`. Regras
  são gerenciáveis via `GET/POST/PATCH/DELETE /findings/fp-rules` (listar,
  adicionar à mão, ativar/desativar, remover).
- `FP_BLACKLIST` (env) funciona como **seed imutável**, mesclada com as regras
  aprendidas habilitadas no momento da validação. `FP_LEARNING=false` desliga o
  aprendizado (a gestão manual continua). Aprendizado vem **só** de decisão
  humana — vereditos do LLM juiz nunca geram regra (evita aprender ruído do
  modelo). O efeito é prospectivo: não revalida retroativamente candidatos de
  runs anteriores.

---

## Etapa 7 — Economia de Tokens (RTK + Caveman)

**Status:** `[x]` Concluída (compressão de histórico por resumo de LLM permanece deliberadamente adiada — ver observações)

**Objetivo:** reduzir o consumo de tokens sem perder qualidade de decisão.

**Entregáveis**
- [x] Compactação de saída de tools ("RTK ou equivalente") — `app/llm/compress.py::compact_tool_output`,
      aplicada em `app/tools/executor.py` quando `TOOL_OUTPUT_COMPRESSION=true`: remove
      recursivamente chaves/itens nulos ou vazios (nunca remove `0`/`False`, que são dado real)
      e reserializa o corpo JSON de respostas HTTP de forma minificada. Nenhum agente hoje
      injeta saída de tool diretamente num prompt de LLM — é infraestrutura pronta para quando
      isso acontecer, mas já reduz de verdade o JSON que a API de tools devolve ao operador.
- [x] Estilo Caveman nas mensagens de saída (`app/llm/compress.py::caveman_compress`, aplicado em `app/llm/client.py` quando `CAVEMAN_PROMPTS=true`) — remove palavras de enchimento das mensagens enviadas aos providers
- [x] Cache agressivo de resultados de APIs e contexto (Etapa 3 — `app/llm/cache.py`, `LLM_CACHE_ENABLED`/`LLM_CACHE_TTL_SECONDS`)
- [x] Compressão de histórico entre nós do grafo (`app/llm/compress.py::compress_history`, aplicada no wrapper de nó em `app/orchestration/graph.py` quando `HISTORY_COMPRESSION=true`; mantém o primeiro + últimos `HISTORY_KEEP_LAST` registros, deterministicamente, sem chamada de LLM)
- [x] Orçamento hard por run (já existia em `should_continue`: `tokens_used >= budget_tokens` ou `cost >= budget_cost` → para); agora registra `stop_reason="budget"` (e `"confidence"` no fim por confiança) para observabilidade — `app/orchestration/graph.py` + `app/agents/builtin.py`
- [x] Orçamento hard por agente — `BUDGET_TOKENS_PER_AGENT`/`BUDGET_COST_PER_AGENT` (desligado por
      padrão), checado em `should_continue` contra o PRÓXIMO agente que executaria (relevante só
      para Eremita/Carro no modo padrão, que podem repetir); motivo de parada `stop_reason="agent_budget"`.
      Contadores acumulados por agente em `GraphState.tokens_by_agent`/`cost_by_agent` (via `_apply_llm`).
- [~] Compressão de histórico por resumo de LLM — permanece deliberadamente adiada (ver observações)

**Critérios de aceite**
- [x] Redução de tokens mensurável quando os levers estão ligados — números reais medidos e
      travados por asserção em `tests/test_token_savings_measurement.py`:

      | Lever | Amostra | Antes → Depois | Redução |
      |---|---|---|---|
      | Caveman (contexto verboso/conversacional) | frase de instrução típica de operador | 276 → 188 caracteres | ~32% |
      | Caveman (prompt de sistema já enxuto) | `HermitAgent.system_prompt()` real | 524 → 486 caracteres | ~7% (esperado — o lever ajuda pouco em texto já escrito de forma direta) |
      | Compactação de tool output | resposta realista estilo AbuseIPDB (campos opcionais nulos) | 391 → 269 bytes (JSON) | ~31% |
      | Compressão de histórico | 20 entradas realistas de `history` | 6490 → 2924 bytes (JSON), 20 → 9 entradas | ~55% |

      Medição por contagem de caracteres/bytes (não há tokenizer integrado ao projeto) — proxy
      razoável, não uma contagem de tokens exata.
- [x] Qualidade das decisões não degrada no modo padrão (levers DESLIGADOS por padrão; suíte de 262 testes verde).

**Observações / pendências**
- **Compressão de histórico por resumo de LLM** fica de fora por decisão: usar uma chamada de LLM
  pra resumir e economizar tokens é uma troca (custo/latência da chamada de resumo vs. economia
  no prompt seguinte; risco do resumo perder nuance) que não deveria ser ligada silenciosamente —
  é uma decisão de produto, não uma implementação técnica pendente. A alternativa determinística
  (`compress_history`, mantém primeiro + últimos N) já está implementada e cobre o caso de uso
  sem esse risco.
- Os levers são **opt-in** (`CAVEMAN_PROMPTS`, `HISTORY_COMPRESSION`, `TOOL_OUTPUT_COMPRESSION`,
  `BUDGET_TOKENS_PER_AGENT`/`BUDGET_COST_PER_AGENT`) e offline-determinísticos, então não afetam
  runs existentes nem os testes a menos que habilitados.
- Cobertura: `tests/test_token_economy.py` (caveman, compress_history, orçamento por run/agente,
  compactação de tool output, wrapper de nó) e `tests/test_token_savings_measurement.py`
  (números reais de redução, travados por asserção).

---

## Etapa 8 — Interface e Composição Visual

**Status:** `[x]` Concluído

**Objetivo:** permitir que o usuário monte e execute grafos de arquétipos de forma intuitiva.

**Entregáveis**
- [x] Frontend Vite + React + React Flow scaffoldado (`frontend/`)
- [x] Componentes visuais iniciais (Card, CardNode, canvas, mock de agents/sessions)
- [x] CLI completa (Typer/Rich)
- [x] Canvas funcional de arquétipos (drag-and-drop + conexões) — mão virou paleta; pasta nós no canvas; sequência = posição X (esquerda→direita), `justice` obrigatório à direita
- [x] Visualização do grafo em execução e do estado — `streamRun` (SSE `/runs/stream`) destaca o nó ativo (`is-active`) e marca o nó final como concluído (`is-ended`); arquétipos do grafo passados como `?archetypes=...`
- [x] Exportação de configuração de grafo (YAML/JSON) — `argus compose export` + REST (`/runs/{id}/export` JSON/Markdown, findings CSV)
- [x] Integração com backend (SSE + dados reais) — composição real: `POST /compositions`, `POST /compositions/{id}/execute`, persistência em `sessions.config`, reuso de `validate_sequence`/`Director`; `createRun`/`createTarget` ativados no client
- [x] Painel de execução na UI (`RunPanel`) — abas **Log** (trace ao vivo por passo), **Chat** (raciocínio de cada arquétipo a partir do histórico SSE) e **Resultados** (findings, tabela de trace, tokens/custo, `stop_reason`); substitui o resumo de uma linha
- [x] Lock de run único (1 alvo por vez) — guard no backend em `POST /runs`, `GET /runs/stream` e `POST /compositions/{id}/execute` (409 quando há run `running`/`pending_review`); `GET /runs/active` exposto; frontend desabilita Executar e faz polling do lock
- [x] Cancelamento de run em execução — `POST /runs/{id}/cancel` (sinal checado entre nós no `stream_run`) + botão Cancelar no painel
- [x] Execução unificada via SSE — `/runs/stream?session_id=...` executa composição salva com o mesmo live log/cancel do build manual; tela Sessões passou a usar esse fluxo
- [x] Resultado final explícito — ao concluir, o painel salta para a aba **Resultados** com resumo (tokens, custo, duração, `stop_reason`, alvo) e achados com `severity`/`description`; findings persistidos (`GET /runs/{id}/findings`) têm prioridade sobre o estado bruto do `result`
- [x] Ver resultado de runs antigos — coluna **Ver** no Dashboard e em Sessões abre o RunPanel em modo somente-leitura (`getRun` + `listFindings`, no `App.tsx` via `openReport`)

**Critérios de aceite**
- [x] Criar, salvar e executar um grafo completo pela interface (composições persistidas no backend, executáveis e carregáveis do modal Sessões; carregar-para-editar reconstrói o grafo no canvas)
- [x] Visualizar o grafo em execução com destaque do nó ativo via SSE
- [x] Ver progresso/log ao vivo durante a execução e resultados completos após a conclusão
- [x] Iniciar um novo run é bloqueado enquanto houver um ativo (incluindo `pending_review`), mesmo após refresh da página
- [x] Cancelar um run em andamento pela interface

**Pontos a discutir**
1. CLI-first ou web-first.
2. Como representar os arquétipos e conexões visualmente.
3. Arrastar-conectar vs configuração declarativa.
4. Feedback em tempo real do progresso do grafo.
5. Como o usuário injeta input humano (HITL) pela interface.

---

## Etapa 9 — Integrações Externas (Informação)

**Status:** `[x]` Concluído

**Objetivo:** conectar fontes de dados fornecidas pelo operador (banco de CVEs, exploits, bancos
OSINT) de forma controlada e cacheada, sem wrappers embutidos.

**Entregáveis**
- [x] Camada de plugin/config para fontes de dados fornecidas pelo operador (CVE, exploits, OSINT) — `sources.json` → `DataSourceRegistry`
- [x] Cache de CVE e dados externos no SQLite (`CveCache`, `ExternalDataCache` + TTL)
- [x] Rate limiting e normalização de respostas (`DataSourceService`)
- [x] Política de "só o necessário" (minimização de dados — campos declarados por fonte)

**Critérios de aceite**
- [x] Agentes obtêm dados normalizados via registry sem conhecer a fonte específica
- [x] Tudo é cacheado e auditado (cache + logging de invocação)
- [x] Uma nova fonte (ex.: banco OSINT) é adicionada via config sem mudar o código do backend

**Observações / pendências**
- Integração com agentes: `DataSourceService` é injetado no `GraphState` (`set_sources_service`)
  em `create_run`, `event_stream`, execute de composição e CLI. Agentes consultam
  `service.available_sources()` + `service.query(...)` via `_collect_sources`, sem conhecer a
  fonte específica. Resultados normalizados ficam no campo serializável `state.sources`
  (auditoria/persistência); o serviço em si é `PrivateAttr` (não serializa/não vaza).
- Fallback determinístico: sem fonte configurada ou falha de rede, retorna dados simulados estáveis
  (mantém testes offline). Manifesto `sources.json` traz fontes placeholder que o operador configura.
- Fontes são read-only; minimização restringe os campos retornados ao necessário.

**Pontos a discutir**
1. Quais fontes priorizar no MVP.
2. Estratégia de cache e atualização.
3. Como o orquestrador decide quando consultar uma fonte externa.
4. Tratamento de dados sensíveis retornados pelas fontes.

---

## Etapa 10 — Observabilidade, HITL e Hardening para Produção

**Status:** `[x]` Concluída

**Objetivo:** tornar o sistema confiável, auditável e seguro para uso real (apenas ambientes autorizados).

**Entregáveis**
- [x] Logging estruturado (parcial — Etapa 0)
- [x] Kill-switch operacional (parcial — Etapa 0)
- [x] Tracing de decisões do grafo — campo `trace` estruturado no estado (nó, ação, timestamps, duração, tokens, custo, provider, model, strategy) populado pela tabela `agent_runs`; `GET /runs/{id}/trace`
- [x] Dashboard de runs, custos e findings — agregados `GET /dashboard/summary` e `GET /dashboard/runs` + aba Dashboard no frontend (cards e tabela de runs)
- [x] Mecanismo robusto de Human-in-the-Loop — `app/orchestration/hitl.py` + API `POST /runs/{id}/review`; chariot exige aprovação p/ ação destrutiva e hermit sinaliza finding p/ revisão; runs em `pending_review` param no nó `human_gate` e são retomados após decisão; verdicts gravados como `decisions`; CLI `argus compose pending` / `review`
- [x] Relatórios (Markdown, JSON, SARIF) — export `format=sarif` adicionado ao `GET /runs/{id}/export` (SARIF 2.1.0); PDF futuramente
- [x] Hardening (timeouts, resource limits, secret scanning) — ver detalhe abaixo
- [x] Documentação de operação e runbooks — `docs/RUNBOOK.md`

**Critérios de aceite**
- [x] Qualquer run pode ser completamente auditado e reproduzido a partir de logs + estado.
- [x] Existe kill-switch e HITL funcional.

**Detalhe — Hardening**
- **Secret scanning/redação** (`app/core/secrets.py`): padrões heurísticos (chave AWS,
  token GitHub/Slack, JWT, bloco de chave privada PEM, atribuição genérica
  `key=value`). Aplicado em dois pontos:
  - Todo log estruturado (`app/core/logging.py`) — mensagem e campos `extra`
    (recursivamente em dict/list) são redigidos antes de virar JSON.
  - Toda mensagem enviada a um provider de LLM (`app/llm/client.py`) — nunca
    encaminha um segredo descoberto durante a investigação a um provider terceiro.
  - Deliberadamente **não** aplicado à `EvidenceStore` — uma credencial exposta é
    frequentemente o próprio finding; redigir ali destruiria a evidência.
- **Timeout + kill de subprocesso** (`app/tools/executor.py`): ao estourar
  `ToolSpec.timeout`, o processo filho agora é morto (`process.kill()`) — antes
  desta etapa o timeout cancelava a espera mas deixava o processo rodando em
  segundo plano.
- **Resource limits de subprocesso** (POSIX only, no-op no Windows):
  `RLIMIT_AS` via `TOOL_SUBPROCESS_MEMORY_LIMIT_MB` (default 512MB) e
  `RLIMIT_NOFILE` fixo em 256, aplicados via `preexec_fn`. Testado de ponta a
  ponta: um subprocesso tentando alocar 500MB com teto de 64MB efetivamente
  morre (não é só configuração aceita e ignorada).
- **Truncamento de saída**: stdout/stderr de tool CLI cortados em
  `TOOL_SUBPROCESS_MAX_OUTPUT_BYTES` (default 64KB) antes de entrar no histórico
  ou em qualquer log.
- Cobertura: `tests/test_hardening.py` (20 testes) — suíte completa em
  178 testes verdes, `ruff` limpo.

**Runbooks** (`docs/RUNBOOK.md`): subida do serviço, kill-switch, fila HITL,
cada controle de hardening acima com seu próprio runbook de incidente, backup/
recuperação de banco e evidências, e leitura de log.

---

## Etapa 11 — Relatório de Segurança

**Status:** `[x]` Concluída

**Objetivo:** dar substância ao entregável final — um relatório de pentest/bug bounty que
responda **o que foi achado, por que é uma vulnerabilidade, qual a gravidade, quais
CVEs/exploits conhecidos e como mitigar** — em vez de apenas tokens/custo/status.

**Entregáveis**
- [x] Modelo de finding estruturado (`app/db/models/finding.py`) com `category`, `affected`,
  `cvss_score`, `cvss_vector`, `cves`, `known_exploits`, `remediation`, `references`
  (+ migração Alembic `0c11d25e9cb6` e `FindingRead`).
- [x] Achados com a forma final (severidade real, CVE, exploit público, remediação,
  evidência, referências) — inicialmente via scanner simulado determinístico
  (`app/services/demo_findings.py`), substituído na Etapa 13 por fontes de dados e
  correlação reais (`app/services/source_findings.py` + `app/services/cve_correlate.py`).
- [x] Arquétipos (Eremita/Carro) emitem achados ricos; severidade vem do dado do achado
  (não mais derivada da confiança).
- [x] Relatório estruturado `GET /runs/{id}/report` (`summary` + `findings[]` +
  `observability`) e `GET /runs/{id}/export` (markdown/JSON/CSV/SARIF) reescritos em
  torno dos achados; tokens/custo viram apêndice de observabilidade.
- [x] UI de resultados (`FindingCard` + aba Resultados) com badge de severidade, CVEs,
  flag de exploit público e remediação; observabilidade recolhível.
- [x] Política de conteúdo formalizada (`docs/adr/0005-reporting.md`): **relatar ≠ ensinar**.

**Critérios de aceite**
- [x] Um run concluído reporta achados com severidade, CVEs, exploits conhecidos e
  remediação (não mais "Candidate signal …" genérico).
- [x] Tokens/custo não ocupam mais o centro do relatório (apêndice de observabilidade).
- [x] Tudo determinístico offline (nenhuma dependência de rede/API para gerar o relatório).

---

## Etapa 12 — Scanning Ativo (OWASP Top 10)

**Status:** `[x]` Concluída

**Objetivo:** o Argus Engine precisa interagir com o alvo para encontrar vulnerabilidades
reais. Scanning ativo é funcionalidade core — sempre roda quando o alvo está em
`ALLOWED_SCOPES`, independentemente do Modo Diabo. Ver `docs/adr/0006-active-scanning.md`.

**Entregáveis**
- [x] Módulo `app/scanning/` — HTTP client com rate limiting e timeout
- [x] Download e parsing de página HTML (análise de conteúdo, forms, links)
- [x] Análise de headers de resposta (segurança, cookies, CORS, CSP)
- [x] Crawl de links internos e extração de endpoints
- [x] Fingerprinting de tecnologias (server, framework, linguagem, versão)
- [x] Detecção de vulnerabilidades OWASP Top 10 (vetores passivos — forms, parâmetros, headers)
- [x] Integração com `HermitAgent` (scanning ativo + OSINT passivo)
- [x] Rate limiting por target (`SCAN_RATE_LIMIT`, configurável)
- [x] Timeout por requisição (`SCAN_REQUEST_TIMEOUT`, configurável)
- [x] Self-imposed restrictions (respeitar `robots.txt`, não executar payloads destrutivos)
- [x] Logging completo de todas as requisições ao alvo
- [x] Findings com evidência de scanning real (respostas HTTP, headers, conteúdo)
- [x] Controles de segurança: scanning só com alvo em `ALLOWED_SCOPES`

**Critérios de aceite**
- [x] Um run contra um alvo em `ALLOWED_SCOPES` gera findings de scanning ativo (download de página, análise de headers, detecção de vulnerabilidades)
- [x] Scanning ativo NÃO depende do `DEVIL_MODE` — roda com escopo validado
- [x] Rate limiting e timeout funcionam (configuráveis via env)
- [x] `robots.txt` é respeitado (self-imposed restriction)
- [x] Todas as requisições ao alvo são logadas
- [x] Findings de scanning ativo têm evidência real (resposta HTTP, header, conteúdo)

**Observações / pendências**
- Scanning ativo é separado do Modo Diabo — este é para execução destrutiva/futura (exploits)
- Detecção de vulnerabilidades é passiva (análise de resposta, não injeção de payloads) —
  injeção real de payloads (SQLi, XSS) ficaria no Modo Diabo futuro
- O módulo de scanning pode ser expandido para incluir login dinâmico:
  **slice 1 (auth estática por env — `SCAN_EXTRA_HEADERS`/`SCAN_COOKIES`) e
  slice 2 (login dinâmico — `SCAN_LOGIN_URL`/`SCAN_LOGIN_USERNAME`/`SCAN_LOGIN_PASSWORD`,
  submete o form, mantém sessão via cookie jar) já entregues**;
  usos avançados (MFA, OAuth, re-login automático, credenciais por target) ficam para trás.

---

## Etapa 13 — Integração de Ferramentas Reais

**Status:** `[x]` Concluída

**Objetivo:** fechar o seam aberto na Etapa 11 — onde o "scanner simulado"
(`app/services/demo_findings.py`) gerava achados de demonstração para servir de
molde. Agora o pipeline deriva findings de **fontes de dados reais** (NVD, CISA KEV,
CVE.report, OSINT) e correlaciona banners/fingerprints do scanning ativo a CVEs
conhecidos. Ver `docs/adr/0008-cve-correlation.md`.

**Entregáveis**
- [x] Deletado o scanner simulado (`app/services/demo_findings.py`) — nenhum import restante
- [x] Extractors de findings baseados em respostas reais (`app/services/source_findings.py`):
  abuseipdb, crtsh, nvd, **urlscan**, **ip_api**; respostas simuladas/irreconhecíveis são
  ignoradas (nunca fabrica valor)
- [x] Correlação CVE por produto+versão do banner (`app/services/cve_correlate.py`):
  NVD keywordSearch (`resultsPerPage`; sem `keywordExactMatch` — a API 2.0 o
  rejeita com 404, validado ao vivo), CISA KEV (catálogo
  full-feed como source `kev`, `skip_sweep`), CVE.report (ID → refs + EPSS/KEV)
- [x] Findings de correlação sempre `status="candidate"` + `requires_human_review=True`
  (correlação é lead textual, não confirmação); degradação offline determinística
  (sem dado real → zero findings)
- [x] Wiring no `HermitAgent.run` — correlação roda após o scanning ativo; resultado
  contabilizado no entry como `cve_correlations`
- [x] Tools reais de rede no registry (`backend/tools.json`): `whois`, `dig`
  (CLI, `sandbox_network`, `destructive: false`)
- [x] `skip_sweep` em `DataSourceSpec` (`app/sources/spec.py`) — fontes a consultar sob
  demanda (KEV) ficam fora do sweep genérico do agente
- [x] Knob `CVE_CORRELATE_MAX_CVES` (`app/core/config.py`, default 5)

**Critérios de aceite**
- [x] Banner `Apache/2.4.49` no scanning ativo gera um finding `candidate` listando
  o CVE com KEV/exploit conhecido, severidade CVSS e referências
- [x] Sem rede/chave/resultado NVD → nenhum finding de correlação (degradação silenciosa)
- [x] Nenhuma fonte simulada gera finding (testado em `tests/test_real_sources.py`)
- [x] `ruff check app tests` e `pytest -q` verdes

**Observações / pendências**
- `cve_report` segue sem extractor próprio no sweep — seu papel é o enriquecimento
  dentro da correlação (`cves`/`references`/EPSS/KEV por CVE)
- Correlação só dispara com versão no banner (produto sem versão é ruído)
- Sources novas para adicionar depois: Censys/Shodan, whois passivo, certstream
- `whois`/`dig` integrados ponta a ponta como tools operator-invoked: `argus tools run
  <tool> <target>` (CLI) e `POST /tools/{name}/invoke` validam o alvo contra
  `ALLOWED_SCOPES` e degradam de forma determinística quando o binário não está
  instalado (`FileNotFoundError` → `ToolExecutionError`, nunca 500). Eremita não faz
  shell-out para elas por design (agente só lê das sources configuradas).
- **Frontend**: o bubble do Eremita na aba Chat agora mostra o meta do entry —
  `cve_correlations` (chips "N correlações CVE"), achados, fontes e scan ativo
  (páginas) — propagado do `history` tanto no SSE ao vivo quanto no report
  (`frontend/src/App.tsx` → `ChatMessage` → `RunPanel`).
- **Validação ao vivo** via `python -m app.cli.main sources smoke` (comando da
  Etapa 13): NVD `keywordSearch` não deve levar `keywordExactMatch` (a API 2.0 o
  rejeita com 404); `rate_burst` (default 1) libera o NVD com burst 5 para o
  sweep + correlação rodarem no mesmo run (ver `docs/adr/0008-cve-correlation.md`)
- **E2E ao vivo (run completo) validado**: `compose execute` contra `example.com`
  rodou o caminho lock → grafo → Eremita (simulação + scan ativo) → fontes reais
  (NVD/crtsh/urlscan) → síntese (Mago) → validação (Justiça). Dois bugs reais
  encontrados e corrigidos:
  - **DB lock (CLI)**: `_session_execute` segurava a transação de escrita do
    `Run` durante o grafo inteiro, bloqueando as escritas concorrentes do cache
    em outra conexão → `database is locked`. Fix: `session.commit()` logo após o
    `flush` (o que o API já fazia) + WAL com `busy_timeout=30_000` /
    `synchronous=NORMAL` no engine SQLite (`app/db/session.py`).
  - **Scan vazio (`pages=0`)**: `robots.txt` era buscado via `get_page()`, que
    registrava o rate-limit do host e fazia o 1º request real do crawl estourar
    `Rate limit exceeded`. Fix: `fetch_no_rate_limit()` para requests de
    infraestrutura (`robots.txt` não consome o orçamento do scan) em
    `app/scanning/client.py` + `service.py`.

## Próximos passos sugeridos

> Lista revisada — todos os itens de Etapas 1, 2, 3, 4, 5, 6, 7, 8, 10, 11 e 12
> listados aqui foram entregues (ver status de cada etapa acima). Etapa 7 consta
> como parcial apenas por um item deliberadamente adiado:

- **Etapa 7 — compressão de histórico por resumo de LLM**: decisão de produto
  adiada (custo/latência da chamada de resumo × economia no prompt seguinte e
  risco de perder nuance), não uma pendência técnica. Ver seção da Etapa 7.

## Como manter este documento

A cada etapa, atualize:
- o checkbox da etapa (`[x]`) e o **Status**;
- os entregáveis concluídos (`[x]` em cada item);
- a tabela de **Visão geral**;
- registre decisões em `docs/adr/` (ADR — Architecture Decision Records).
