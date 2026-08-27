# ROADMAP — Argus Engine

Plano vivo de implementação da plataforma de orquestração de agentes para segurança
ofensiva **autorizada**. Este documento é a fonte de verdade das etapas, com o estado
atual do repositório e o que falta em cada fase.

> **Uso autorizado apenas.** Este projeto só deve ser usado em alvos com autorização
> explícita e escopo definido, em conformidade com leis locais e políticas de bug bounty.

---

## Princípios inegociáveis (repetir em toda etapa)

1. Uso exclusivo em alvos com autorização explícita e escopo definido.
2. Nenhum detalhe de técnicas de reconhecimento, exploração, payloads ou chaining.
3. Controles de segurança operacional, logging completo e kill-switch desde o dia 1.
4. Modelos abliterados apenas atrás de policy gateway + sandbox + human-in-the-loop em ações sensíveis.
5. Economia de tokens e observabilidade desde o início.
6. Modo Diabo (execução real de scripts invasivos/destrutivos) só ativável com escopo validado + sandbox + kill-switch + auditoria completa + HITL em ações destrutivas.

---

## Modo Diabo (modo de execução dual)

O **Diabo** deixou de ser um arquétipo e virou um **modo de execução** do sistema — um
toggle global (`DEVIL_MODE`) que muda o comportamento de toda a plataforma.

| Estado | Comportamento |
|---|---|
| **OFF (padrão)** | Apenas **investigação e simulação**. Nenhum ataque real ocorre: os agentes levantam informações e simulam cenários, sem executar scripts invasivos. |
| **ON** | Agentes de **execução** usam modelos **sem restrição** e **executam de fato** scripts invasivos/destrutivos. Os agentes de **julgamento/investigação** permanecem em **modelos fixos (restritos)** para validar, julgar e auditar o que foi feito. |

**Controles sempre obrigatórios (mesmo com o modo ON):** validação de escopo, sandbox
(Docker), kill-switch, auditoria completa e HITL em ações destrutivas.

**Roteamento por modo:** os agentes de execução só têm acesso ao caminho "agressivo"
quando `DEVIL_MODE=ON`; caso contrário, rodam no modo simulado (não-invasivo).

---

## Decisões de stack (já definidas)

### Backend
| Camada | Tecnologia | Status |
|---|---|---|
| Linguagem | Python 3.11+ (ambiente atual: 3.13) | Definida |
| Framework API | FastAPI + Uvicorn | Implementada |
| Orquestração | LangGraph (grafo de agentes com estado tipado) | Implementada |
| Persistência | SQLite + SQLAlchemy 2.0 (async) | Implementada (parcial) |
| Estado do grafo | Pydantic `BaseModel` | Implementado |
| Config | `.env` + pydantic-settings | Implementada |
| Logging | Estruturado (JSON) | Implementado |
| Sandbox | Docker | Pendente (Etapa 5) |
| Modo Diabo | flag `DEVIL_MODE` + HITL em ações destrutivas | Planejado |
| CLI | Typer/Rich | Pendente (Etapa 8) |

### Frontend
| Camada | Tecnologia | Status |
|---|---|---|
| Framework | Vite + React 19 | Scaffold criado |
| Canvas de grafo | `@xyflow/react` (React Flow) | Scaffold criado (mock) |
| Animações | Framer Motion + Rive | Pendente |
| Estado | Zustand | Pendente |
| Estilo | Tailwind + shadcn/ui | Pendente |

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
| 2 | Arquétipos e Personas | Agentes reutilizáveis (Tarot) | 🟡 Parcial |
| 3 | Roteador de LLMs | Gateway multi-provider (OmniRoute-like) | 🟡 Parcial |
| 4 | Persistência e Evidências | SQLite completo + evidências | 🟡 Parcial |
| 5 | Tool Registry e Sandbox | Ferramentas com permissão e isolamento | 🟡 Parcial |
| 6 | Filtro de Qualidade | Anti-falso-positivo | 🟡 Parcial |
| 7 | Economia de Tokens | RTK + Caveman | ⬜ Pendente |
| 8 | Interface e Composição Visual | Canvas de arquétipos | 🟡 Parcial |
| 9 | Integrações Externas | Fontes de dados cacheadas | 🟡 Parcial |
| 10 | Observabilidade, HITL e Hardening | Produção auditável e segura | ⬜ Pendente |

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
- [ ] Execução paralela básica (atualmente sequencial)

**Critérios de aceite**
- [x] É possível definir um grafo de 3 nós, executar e receber estado final tipado.
- [x] Logs estruturados de cada transição de nó (via `history` no estado).

**Observações / pendências**
- Paralelismo de nós não implementado (fase futura).
- `inject_human_input` é stub (será feito na Etapa 10).
- Persistência/retomada de runs usa JSON no estado (retomada real ainda pendente).

---

## Etapa 2 — Arquétipos e Personas

**Status:** `[ ]` Parcial

**Objetivo:** transformar agentes em arquétipos reutilizáveis e composáveis.

**Entregáveis**
- [x] Definição formal de Arquétipo (`app/agents/base.py` — `BaseArchetype`)
- [x] Registry de arquétipos (`app/agents/__init__.py` — `get_archetype`)
- [x] 3 arquétipos mínimos (Imperador/Diretor, Eremita/Coletor, Justiça/Analista)
- [x] Biblioteca completa de 6 arquétipos Tarot (Imperador, Eremita, Louco, Justiça, Carro, Mago)
- [x] Mecanismo de composição (lista ordenada de arquétipos → grafo dinâmico)
- [x] Validação de compatibilidade entre arquétipos (básica: sem duplicatas, termina em `justice`)
- [ ] System prompts completos por persona
- [ ] Schema de saída obrigatório por arquétipo (JSON Schema)
- [ ] Modo Diabo como perfil de execução (ver seção "Modo Diabo")

**Critérios de aceite**
- [x] Um usuário consegue montar um grafo só com arquétipos e executá-lo (via API, com os 3 mínimos).
- [x] Cada arquétipo declara explicitamente suas tools e limites (`allowed_tools`).
- [x] Montar e executar grafo com os 6 arquétipos.

**Pontos a discutir**
1. Lista final de arquétipos e responsabilidades (sem entrar em técnicas).
2. Versionar prompts de sistema.
3. Separação clara entre "raciocínio" (modelos fortes) e "execução controlada" (menores/abliterados).
4. Como o orquestrador escolhe combinações automaticamente.
5. Nível de customização do usuário vs hardcoded de segurança.
6. Como o Modo Diabo é exposto ao usuário (confirmação/HITL obrigatória ao ligar).

---

## Etapa 3 — Roteador de LLMs (estilo OmniRoute)

**Status:** `[ ]` Parcial

**Objetivo:** gateway unificado OpenAI-compatible com múltiplos providers, combos e fallback.

**Entregáveis**
- [x] Cliente unificado
- [x] Suporte a Groq, OpenRouter, OpenAI (OpenAI-compat); Google AI pendente
- [x] Estratégias de combo priority e fallback
- [ ] Estratégias de combo cost-optimized e auto
- [x] Tracking de tokens e custo por chamada
- [x] Headers de decisão (qual modelo/provider foi usado)
- [ ] Cache de prefixo e compressão
- [x] Roteamento por modo: modelos sem restrição p/ execução (Modo Diabo ON) vs modelos fixos p/ julgamento/investigação

**Critérios de aceite**
- [x] Trocar de provider não exige mudança no código dos agentes (agentes chamam o gateway via `LLMRouter`/`attempt_completion`).
- [x] Toda chamada registra tokens, custo e decisão de roteamento.

**Observações / pendências**
- Google Gemini exige adapter nativo (fora desta fatia).
- `cost-optimized`/`auto`, cache de prefixo e compressão ficam para o fim da etapa.
- Wiring dos 6 arquétipos feito com fallback offline determinístico: sem API key (ou falha de provider) os nós degradam à lógica simulada, mantendo o grafo determinístico/offline nos testes (62 testes verdes). Chariot usa o pool de execução quando Modo Diabo ON; os demais usam o pool de julgamento.

**Pontos a discutir**
1. Do zero vs adaptar OmniRoute ou similar.
2. Mapear "tarefa → combo ideal" (orquestração vs execução vs validação).
3. Tratamento de rate limits e quotas free-tier.
4. Onde aplicar policy gateway antes de modelos abliterados.
5. Como o Modo Diabo altera o pool de modelos disponíveis para execução.

---

## Etapa 4 — Persistência e Evidências (SQLite)

**Status:** `[ ]` Parcial

**Objetivo:** tudo que importa fica local, auditável e consultável.

**Entregáveis**
- [x] Models base (`Target`, `Run`) com SQLAlchemy async + SQLite
- [x] Camada de acesso (`app/db/session.py`)
- [x] Schema parcial (`findings`, `evidence`, `decisions`, `agent_runs`, `api_usage`)
- [x] Schema restante (`sessions`, `cve_cache`, `external_data_cache`)
- [x] Migrações (Alembic) — `alembic upgrade head` no startup + `make migrate`
- [x] Armazenamento de evidências (arquivos + metadados + hash SHA-256)
- [x] Exportação de findings (JSON, Markdown)
- [ ] Exportação SARIF
- [x] Isolamento por run (consultas escopadas por `run_id`/`target_id`)

**Critérios de aceite**
- [x] Um run completo grava e recupera todo o estado (via `Run.result` JSON).
- [x] É possível consultar histórico de um target (listar runs por target_id).
- [x] Findings com estados `candidate → validated → false_positive → discarded`.

**Observações / pendências**
- `sessions` (agrupamento) e os caches externos (`cve_cache`, `external_data_cache`) ficam para a Etapa 9 / fatia seguinte.
- Alembic será introduzido quando o schema estabilizar (atualmente `create_all`).

---

## Etapa 5 — Tool Registry e Sandbox

**Status:** `[ ]` Parcial

**Objetivo:** expor ferramentas fornecidas pelo operador (CLI, exploits, OSINT, CVE) atrás de um
registry com permissões e isolamento. A plataforma orquestra; as ferramentas e fontes são plugadas via configuração.

**Entregáveis**
- [x] Camada de plugin/config para registrar ferramentas fornecidas pelo operador (manifesto `tools.json` via `TOOLS_MANIFEST`)
- [x] Tool Registry (nome, descrição, kind http/cli, permissões por arquétipo)
- [x] Executor leve (subprocess com timeout / HTTP via httpx)
- [ ] Executor com sandbox (Docker preferencialmente)
- [x] Rate limiting e timeouts por tool
- [x] Logging de toda invocação

**Critérios de aceite**
- [x] Um agente só consegue chamar tools explicitamente permitidas no seu arquétipo.
- [x] Toda execução de tool é logada e limitada por tempo/taxa.
- [x] Uma ferramenta CLI/API fornecida pelo operador é registrada via config sem mudar o código do backend.

**Observações / pendências**
- Sandbox Docker real fica para uma fatia seguinte (isolamento atual: timeout + rate limit + gating por `devil_mode`).
- Tools `destructive: true` só executam com `devil_mode` ON.

**Pontos a discutir**
1. Formato de declaração das ferramentas fornecidas pelo operador (YAML/JSON/manifesto).
2. Nível de isolamento necessário (Docker, firejail, ou mais leve no início).
3. Política de allowlist vs denylist de comandos/ferramentas.
4. Como o Modo Diabo (ON) libera o acesso a tools destrutivas que ficam bloqueadas no modo OFF.

---

## Etapa 6 — Filtro de Qualidade (Anti-Falso-Positivo)

**Status:** `[ ]` Parcial

**Objetivo:** só findings com evidência e scoring sobem de "candidate" para "validated".

**Entregáveis**
- [x] Pipeline de validação (`app/services/quality.py`)
- [x] Scoring de confiança (regras: confidence + evidências + severidade)
- [x] Validação por regras (scoring + exigência de evidência + blacklist)
- [x] Agente Validador com LLM juiz (usa o gateway da Etapa 3) — `app/services/judge.py`
- [x] Blacklist / local knowledge de falsos positivos conhecidos
- [x] Estados claros no schema (`score`, `requires_human_review`, `validated_at`)
- [x] HITL obrigatório para severidade alta (flag `requires_human_review`)

**Critérios de aceite**
- [x] Nenhum finding chega a "validated" sem passar pelo pipeline (`candidate → validated` só via `/validate`).
- [x] É possível marcar falsos positivos e manter local knowledge (blacklist configurável via `FP_BLACKLIST`).

**Observações / pendências**
- LLM juiz (`LLMJudge`) consulta o gateway (pool de julgamento) em `POST /findings/{id}/validate`, refinando as regras: blacklist, severidade alta e ausência de evidência permanecem proteções inegociáveis que o LLM não sobrescreve (HITL preservado). Sem chave ou falha de provider, degrada ao scoring por regras (offline). Veredito/razão/custo ficam em `Finding.meta["judge"]`.
- Aprendizado de falsos positivos hoje é manual (operador edita a blacklist).

---

## Etapa 7 — Economia de Tokens (RTK + Caveman)

**Status:** `[ ]` Pendente

**Objetivo:** reduzir drasticamente o consumo de tokens sem perder qualidade de decisão.

**Entregáveis**
- [ ] Integração RTK (ou equivalente) para saídas de tools
- [ ] Estilo Caveman nos system prompts e comunicações entre agentes
- [ ] Cache agressivo de resultados de APIs e contexto
- [ ] Compressão de histórico entre nós do grafo
- [ ] Orçamento hard por run e por agente

**Critérios de aceite**
- [ ] Medição mostra redução significativa de tokens em runs de referência.
- [ ] Qualidade das decisões do grafo não degrada de forma mensurável.

---

## Etapa 8 — Interface e Composição Visual

**Status:** `[ ]` Parcial

**Objetivo:** permitir que o usuário monte e execute grafos de arquétipos de forma intuitiva.

**Entregáveis**
- [x] Frontend Vite + React + React Flow scaffoldado (`frontend/`)
- [x] Componentes visuais iniciais (Card, CardNode, canvas, mock de agents/sessions)
- [ ] CLI completa (Typer/Rich)
- [ ] Canvas funcional de arquétipos (drag-and-drop + conexões)
- [ ] Visualização do grafo em execução e do estado
- [ ] Exportação de configuração de grafo (YAML/JSON)
- [x] Integração com backend (SSE + dados reais) — sessões e criação de run deixam de usar mocks

**Critérios de aceite**
- [ ] Criar, salvar, carregar e executar um grafo completo pela interface.

**Pontos a discutir**
1. CLI-first ou web-first.
2. Como representar os arquétipos e conexões visualmente.
3. Arrastar-conectar vs configuração declarativa.
4. Feedback em tempo real do progresso do grafo.
5. Como o usuário injeta input humano (HITL) pela interface.

---

## Etapa 9 — Integrações Externas (Informação)

**Status:** `[ ]` Parcial

**Objetivo:** conectar fontes de dados fornecidas pelo operador (banco de CVEs, exploits, bancos
OSINT) de forma controlada e cacheada, sem wrappers embutidos.

**Entregáveis**
- [x] Camada de plugin/config para fontes de dados fornecidas pelo operador (CVE, exploits, OSINT) — `sources.json` → `DataSourceRegistry`
- [x] Cache de CVE e dados externos no SQLite (`CveCache`, `ExternalDataCache` + TTL)
- [x] Rate limiting e normalização de respostas (`DataSourceService`)
- [x] Política de "só o necessário" (minimização de dados — campos declarados por fonte)

**Critérios de aceite**
- [ ] Agentes obtêm dados normalizados via registry sem conhecer a fonte específica (integração com agentes fica para fatia futura)
- [x] Tudo é cacheado e auditado (cache + logging de invocação)
- [x] Uma nova fonte (ex.: banco OSINT) é adicionada via config sem mudar o código do backend

**Observações / pendências**
- Fatia atual expõe fontes via `app/sources/` + API (`GET /sources`, `POST /sources/{name}/query`).
  Agentes/grafo ainda não consultam fontes diretamente — extensão futura.
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

**Status:** `[ ]` Pendente

**Objetivo:** tornar o sistema confiável, auditável e seguro para uso real (apenas ambientes autorizados).

**Entregáveis**
- [x] Logging estruturado (parcial — Etapa 0)
- [x] Kill-switch operacional (parcial — Etapa 0)
- [ ] Tracing de decisões do grafo
- [ ] Dashboard de runs, custos e findings
- [ ] Mecanismo robusto de Human-in-the-Loop
- [ ] Relatórios (Markdown, JSON, futuramente SARIF/PDF)
- [ ] Hardening (timeouts, resource limits, secret scanning)
- [ ] Documentação de operação e runbooks

**Critérios de aceite**
- [ ] Qualquer run pode ser completamente auditado e reproduzido a partir de logs + estado.
- [ ] Existe kill-switch e HITL funcional.

---

## Próximos passos sugeridos

1. **Etapa 2** — completar os 6 arquétipos Tarot (`emperor`, `hermit`, `fool`, `justice`, `chariot`, `magician`) com system prompts e stubs; implementar o Modo Diabo como perfil de execução.
2. **Etapa 1 (complemento)** — adicionar `devil_mode` ao estado + desvio condicional simular/executar.
3. **Etapa 3** — LLM Gateway multi-provider com roteamento por modo (execução sem restrição vs julgamento fixo).
4. **Etapa 4** — Alembic + schema completo (findings, evidence, decisions, api_usage).
5. **Etapa 5** — camada de plugin/config para ferramentas fornecidas pelo operador.
6. **Etapa 8** — conectar o frontend ao backend via SSE/WebSocket.
7. **Etapa 6** — filtro de qualidade (anti-falso-positivo).

## Como manter este documento

A cada etapa, atualize:
- o checkbox da etapa (`[x]`) e o **Status**;
- os entregáveis concluídos (`[x]` em cada item);
- a tabela de **Visão geral**;
- registre decisões em `docs/adr/` (ADR — Architecture Decision Records).
