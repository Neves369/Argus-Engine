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
| 3 | Roteador de LLMs | Gateway multi-provider (OmniRoute-like) | ⬜ Pendente |
| 4 | Persistência e Evidências | SQLite completo + evidências | 🟡 Parcial |
| 5 | Tool Registry e Sandbox | Ferramentas com permissão e isolamento | ⬜ Pendente |
| 6 | Filtro de Qualidade | Anti-falso-positivo | ⬜ Pendente |
| 7 | Economia de Tokens | RTK + Caveman | ⬜ Pendente |
| 8 | Interface e Composição Visual | Canvas de arquétipos | 🟡 Parcial |
| 9 | Integrações Externas | Fontes de dados cacheadas | ⬜ Pendente |
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
- [ ] `devil_mode` no `GraphState` + desvio condicional simular (OFF) vs executar (ON)
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
- [ ] Biblioteca completa de 6 arquétipos Tarot (faltam Louco, Carro, Mago)
- [ ] Mecanismo de composição (usuário escolhe e conecta)
- [ ] Validação de compatibilidade entre arquétipos
- [ ] System prompts completos por persona
- [ ] Schema de saída obrigatório por arquétipo (JSON Schema)
- [ ] Modo Diabo como perfil de execução (ver seção "Modo Diabo")

**Critérios de aceite**
- [x] Um usuário consegue montar um grafo só com arquétipos e executá-lo (via API, com os 3 mínimos).
- [x] Cada arquétipo declara explicitamente suas tools e limites (`allowed_tools`).
- [ ] Montar e executar grafo com os 6 arquétipos.

**Pontos a discutir**
1. Lista final de arquétipos e responsabilidades (sem entrar em técnicas).
2. Versionar prompts de sistema.
3. Separação clara entre "raciocínio" (modelos fortes) e "execução controlada" (menores/abliterados).
4. Como o orquestrador escolhe combinações automaticamente.
5. Nível de customização do usuário vs hardcoded de segurança.
6. Como o Modo Diabo é exposto ao usuário (confirmação/HITL obrigatória ao ligar).

---

## Etapa 3 — Roteador de LLMs (estilo OmniRoute)

**Status:** `[ ]` Pendente

**Objetivo:** gateway unificado OpenAI-compatible com múltiplos providers, combos e fallback.

**Entregáveis**
- [ ] Cliente unificado
- [ ] Suporte a Google AI, Groq, OpenRouter/Opencode free (extensível)
- [ ] Estratégias de combo (priority, cost-optimized, fallback, auto)
- [ ] Tracking de tokens e custo por chamada
- [ ] Headers de decisão (qual modelo/provider foi usado)
- [ ] Cache de prefixo e compressão
- [ ] Roteamento por modo: modelos sem restrição p/ execução (Modo Diabo ON) vs modelos fixos p/ julgamento/investigação

**Critérios de aceite**
- [ ] Trocar de provider não exige mudança no código dos agentes.
- [ ] Toda chamada registra tokens, custo e decisão de roteamento.

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
- [ ] Schema completo (`sessions`, `agent_runs`, `findings`, `evidence`, `decisions`, `api_usage`, `cve_cache`, `external_data_cache`)
- [ ] Migrações (Alembic) — hoje usa `create_all`
- [ ] Armazenamento de evidências (arquivos + metadados + hash)
- [ ] Exportação de findings (JSON, Markdown, futuramente SARIF)
- [ ] Isolamento por sessão/run (evitar vazamento entre alvos)

**Critérios de aceite**
- [x] Um run completo grava e recupera todo o estado (via `Run.result` JSON).
- [x] É possível consultar histórico de um target (listar runs por target_id).
- [ ] Findings com estados `candidate → validated → false_positive → discarded`.

---

## Etapa 5 — Tool Registry e Sandbox

**Status:** `[ ]` Pendente

**Objetivo:** expor ferramentas fornecidas pelo operador (CLI, exploits, OSINT, CVE) atrás de um
registry com permissões e isolamento. A plataforma orquestra; as ferramentas e fontes são plugadas via configuração.

**Entregáveis**
- [ ] Camada de plugin/config para registrar ferramentas fornecidas pelo operador (CLI, exploits, OSINT, banco de CVEs)
- [ ] Tool Registry (nome, descrição, schema I/O, permissões por arquétipo)
- [ ] Executor com sandbox (Docker preferencialmente)
- [ ] Rate limiting e timeouts por tool
- [ ] Logging de toda invocação

**Critérios de aceite**
- [ ] Um agente só consegue chamar tools explicitamente permitidas no seu arquétipo.
- [ ] Toda execução de tool é logada e limitada por tempo/custo.
- [ ] Uma ferramenta CLI/API fornecida pelo operador é registrada via config sem mudar o código do backend.

**Pontos a discutir**
1. Formato de declaração das ferramentas fornecidas pelo operador (YAML/JSON/manifesto).
2. Nível de isolamento necessário (Docker, firejail, ou mais leve no início).
3. Política de allowlist vs denylist de comandos/ferramentas.
4. Como o Modo Diabo (ON) libera o acesso a tools destrutivas que ficam bloqueadas no modo OFF.

---

## Etapa 6 — Filtro de Qualidade (Anti-Falso-Positivo)

**Status:** `[ ]` Pendente

**Objetivo:** só findings com evidência e scoring sobem de "candidate" para "validated".

**Entregáveis**
- [ ] Pipeline de validação
- [ ] Scoring de confiança
- [ ] Agente Validador (ou regras + LLM juiz)
- [ ] Blacklist / local knowledge de falsos positivos conhecidos
- [ ] Estados claros no schema
- [ ] HITL obrigatório para severidade alta

**Critérios de aceite**
- [ ] Nenhum finding chega a "validated" sem passar pelo pipeline.
- [ ] É possível marcar e aprender com falsos positivos.

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
- [ ] Integração com backend (SSE/WebSocket) — hoje o front usa mocks

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

**Status:** `[ ]` Pendente

**Objetivo:** conectar fontes de dados fornecidas pelo operador (banco de CVEs, exploits, bancos
OSINT) de forma controlada e cacheada, sem wrappers embutidos.

**Entregáveis**
- [ ] Camada de plugin/config para fontes de dados fornecidas pelo operador (CVE, exploits, OSINT)
- [ ] Cache de CVE e dados externos no SQLite
- [ ] Rate limiting e normalização de respostas
- [ ] Política de "só o necessário" (minimização de dados)

**Critérios de aceite**
- [ ] Agentes obtêm dados normalizados via registry sem conhecer a fonte específica.
- [ ] Tudo é cacheado e auditado.
- [ ] Uma nova fonte (ex.: banco OSINT) é adicionada via config sem mudar o código do backend.

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
