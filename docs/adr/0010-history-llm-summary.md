# ADR-0010 — Compressão de histórico por resumo de LLM (Etapa 7)

**Status:** Aceito

## Contexto

A Etapa 7 (Economia de Tokens) implementou a compressão de histórico entre
nós do grafo de forma **puramente determinística** (`compress_history` em
`app/llm/compress.py`): quando `HISTORY_COMPRESSION=true`, o wrapper de nó em
`app/orchestration/graph.py` mantém o primeiro + últimos `HISTORY_KEEP_LAST`
registros e **descarta o meio**. Era barato, offline-safe e determinístico —
com o custo de perder literalmente o conteúdo intermediário da conversa.

Ficou deliberadamente adiada (decisão de produto registrada na Etapa 7) uma
alternativa com **resumo LLM** do trecho intermediário: a troca
(custo/latência da chamada de resumo × economia no prompt seguinte; risco do
resumo perder nuance) não deveria ser ligada silenciosamente.

## Decisão

Hoje, o resumo de histórico passou a existir como **lever opt-in, default ligado
quando a compressão está ativa**:

- Novo **`HISTORY_LLM_SUMMARY`** (`app/core/config.py`, default `true`): só tem
  efeito quando `HISTORY_COMPRESSION=true` (default `false`) — ou seja, o modo
  padrão/offline e os testes continuam determinísticos.
- `app/llm/compress.py::llm_summarize_middle` substitui o trecho intermediário
  por **um único** registro de resumo factual (mantém primeiro + últimos N
  intocados), via `attempt_completion` (mesma fronteira de degrade dos agentes).
- **Uma chamada por run no máximo**: `GraphState.history_summary_done` (campo
  serializável, persiste em resume) marca que o meio já foi resumido; os
  overflows seguintes usam `compress_history` determinístico — limitando o
  custo/latência do resumo, que era exatamente a preocupação que adiava a
  decisão.
- **Degrade determinístico**: sem provider/chave (`attempt_completion → None`)
  ou resumo vazio → `compress_history` (descarta o meio) e o run segue.

## Consequências

- Runs com `HISTORY_COMPRESSION` ligado agora preservam o conteúdo intermediário
  como resumo (menos perda de nuance) ao custo de **1** chamada LLM de resumo por
  run — custo/latência contidos pelo limite de 1-por-run.
- Sem provider (offline/testes) nada muda de comportamento em relação à
  compressão determinística.
- `history_summary_done` é serializado com o estado, então a retomada (Etapa 14)
  preserva a semântica "já resumi" — não resumirá de novo num run retomado.
- Opcional, mas nenhuma migração de banco: o campo vive em `GraphState`.

## Alternativas consideradas

- Manter 100% determinístico (status quo): simples, mas descarta o meio sem
  preservar nada do conteúdo.
- Resumir a cada overflow: presença maior de nuance, porém N chamadas LLM por
  run — rejeitado por custo/latência (motivo original do adiamento).