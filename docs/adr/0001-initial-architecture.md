# ADR-0001 — Arquitetura inicial (backend + frontend + orquestração)

**Status:** Aceito

## Contexto

O Argus Engine nasce como uma plataforma de **pentest e bug bounty autorizada**
com scanning ativo e orquestração de agentes de IA. Antes do primeiro ADR
registrado (0002-alembic), a base do projeto foi decidida de ponta a ponta:
linguagens, frameworks, banco de dados, modelo de orquestração e os controles
de segurança que valem para todas as etapas seguintes.

Os requisitos não-funcionais que dirigiram a escolha:

- **Autorização e escopo como invariante**: todo alvo deve estar em
  `ALLOWED_SCOPES`; relatar não pode ensinar exploração.
- **Orquestração de múltiplos agentes** com estados distintos, streaming para a
  UI, retomada de execução e revisão humana (HITL).
- **Run único global** — um run ativo por vez, com lock e cancelamento.
- **Offline-first nos testes**: o grafo deve ser determinístico e executável
  sem LLM/provider real.
- **Observabilidade e economia de tokens** desde o dia 1 (métricas, logging
  estruturado, compressed prompts).
- **Fácil operação**: um deploy simples de `docker compose`, com caminho de
  produção opcional.

## Decisão

**Backend — Python 3.11+ com FastAPI:**

- `FastAPI` + `SQLAlchemy` 2.0 async + `SQLite` (com Alembic para migrações —
  ver `ADR-0002`). Python pela base madura de ferramentas de segurança e IA;
  FastAPI pelo suporte nativo a `async`, tipagem via Pydantic e SSE.
- **Orquestração por `LangGraph`** com `GraphState` como Pydantic `BaseModel`
  (não `TypedDict`): grafo **sempre supervisionado**, em que o Imperador
  (supervisor) escala os demais arquétipos e fecha o run.
- Persistência do estado de execução em `Run.result` para permitir **retomada**
  de runs cancelados/falhos e revisão HITL.

**Frontend — TypeScript com React + Vite:**

- `React 19` + `Vite` + `@xyflow/react` para a visualização/fluxo inspirado em
  tarô; `Zustand` para estado de UI e `Framer Motion` para animação.
- SPA consumindo a API via proxy `/api`; deploy estático via nginx.

**Modelo de agentes:**

- 6 arquétipos (Imperador/supervisor, Eremita/coletor, Louco/escuta inicial,
  Mago/síntese, Justiça/validação, Carro/execução de tools e verificação),
  cada um herdando de `BaseArchetype` e registrado em `app/agents/__init__.py`.
- **Scanner ativo** (crawl, headers/forms, OWASP Top 10) roda sempre que o
  alvo está em escopo — independente de qualquer modo destrutivo.

**Segurança operacional (controles desde o dia 1):**

- `ALLOWED_SCOPES` validado em toda entrada; **kill-switch** global (runtime e
  env); auth leve por senha única + sessão HMAC; sandbox para execução de tools
  não destrutivas; traveling system para logging/lixa de segredos.

## Consequências

- Python async + FastAPI entrega SSE nativo para streaming de runs e pontes
  simples com o ecossistema de LLM.
- Run único global simplifica o modelo de concorrência (lock em memória +
  recuperação de órfãos), mas impede execução paralela de targets distintos — o
  que será observado se surgir demanda por paralelismo.
- A UI é um **canvas de cartas** (arquétipos), com a abstração de composição
  mapeada sobre o grafo supervisionado; cartas ≠ sequência — é um conjunto.
- Testes permanecem determinísticos sem LLM porque o grafo tem um modo
  simulado completo e o LLM só é acionado quando há provider/chave.
- A stack é opinada e presa: LangGraph amarra o modelo de orquestração; migrar
  para outro runtime de agentes exigiria reescrever `app/orchestration/`.

## Alternativas consideradas

- **NestJS/Node para o backend**: unificar linguagem com o frontend, mas perde
  a maturidade do ecossistema de segurança/IA em Python.
- **Grafos Semantics como máquina de estados manual**: sem LangGraph, um
  orquestrador próprio daria mais controle, porém mais código de manutenção
  (estado, serialização, retomada) para o mesmo resultado.
- **PostgreSQL em vez de SQLite**: mais robusto para produção, porém adiciona
  infraestrutura; SQLite async cobre bem o caso de deploy single-container.
- **Pipeline linear de cartas (sem supervisor)**: rejeitado — não permitia
  repetição de agentes nem decisões dinâmicas do Imperador; ver ADR da
  evolução do supervisor (Parte 4).