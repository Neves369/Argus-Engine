# ADR-0004 — Composição visual do grafo com persistência em `sessions.config`

**Status:** Aceito

## Contexto

A Etapa 8 precisa deitar o fluxo de composição visual do grafo de arquétipos sem
multiplicar tabelas nem duplicar a lógica de orquestração já existente. O backend já
possui `validate_sequence` (em `app/orchestration/compose.py`), o `Director`, o model
`Session` (tabela `sessions`) e endpoints de targets/runs. O frontend (React Flow)
renderizava a mão de cartas em modo **somente leitura** (`nodesDraggable=false`), e os
clientes `createTarget`/`createRun` existiam mas nunca eram utilizados.

Decisões já confirmadas: (1) reusar `sessions` com uma coluna `config` JSON; (2) a
ordem da sequência é definida pela posição X dos nós no canvas (esquerda→direita), com
`justice` obrigatório à direita; (3) a mão de cartas vira a **paleta arrastável** para
adição de nós no canvas.

## Decisão

- **Modelo de dados**: adicionar coluna `config` (JSON, nullable) à tabela `sessions`
  via migração Alembic nova (`dca25e816781`). Uma composição é uma `Session` cujo
  `config` guarda `{archetypes, target, devil_mode}`.
- **API** (`app/api/v1/compositions.py`, prefix `/compositions`):
  - `POST /compositions` — cria a `Session` com `config`, aplicando `validate_sequence`.
  - `GET /compositions`, `GET /compositions/{id}`, `DELETE /compositions/{id}`.
  - `POST /compositions/{id}/execute` — revalida escopo (kill-switch + `validate_scope`),
    resolve/cria `Target` se o `config.target` tiver nome, cria um `Run` ligado à
    `Session` e executa `Director(archetypes).run(state)`, persistindo o resultado
    (reuso de `persist_run_result`). Retorna `{run_id, status}`.
- **Frontend**:
  - `PlayedArea` vira compositor controlado (React Flow genérico tipado,
    `nodes`/`edges` via `useNodesState`/`useEdgesState`): nós **arrastáveis**, edges
    derivados da ordem X como feedback visual.
  - A `Hand` recebe `palette`: clicar numa carta adiciona o nó correspondente ao canvas
    e a devolve à mão (paleta reutilizável).
  - `App.tsx` mantém `CARD_ARCHETYPES` (id→chave de arquétipo), deriva a sequência pela
    posição X, salva via `createComposition` e executa via `executeComposition` +
    `getRun`, exibindo resumo.
  - `Sessions` passa a listar composições salvas com ação **Executar**.

## Consequências

- Sem tabela nova nem schema extra: composição = linha em `sessions` + JSON em `config`.
- A regra de sequência permanece centralizada no backend (`validate_sequence`); o canvas
  só comunica a ordem visual.
- A sequência visual é determinística (posição X), então o estado do grafo é
  serializável e recarregável a partir de `config.archetypes`.
- `createRun` dedicado continua disponível, mas o fluxo principal passa por
  `executeComposition` (que garante persistência de target+run juntamente da composição).
- Carregar-para-editar no canvas e a CLI (Typer/Rich) permanecem pendentes (Etapa 8
  parcial); a execução de composições salvas já é possível pelo modal Sessões.
