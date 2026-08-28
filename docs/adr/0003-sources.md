# ADR-0003 — Fontes de dados externas plugadas com cache e minimização

**Status:** Aceito

## Contexto

A Etapa 9 precisa conectar fontes de dados fornecidas pelo operador (CVE, exploits,
OSINT) de forma controlada e cacheada, sem wrappers embutidos no backend. O projeto já
consolidou um padrão de "registry plugado via manifesto JSON" em `app/tools/`
(`tools.json` → `ToolRegistry` → `ToolExecutor`), e os models `CveCache` /
`ExternalDataCache` já foram migrados na Etapa 4.

Princípios inegociáveis aplicáveis: uso autorizado, minimização de dados ("só o
necessário"), caching, e comportamento determinístico offline para os testes.

## Decisão

- Introduzir `app/sources/` espelhando o padrão de `app/tools/`:
  - `DataSourceSpec` (Pydantic): fonte declarativa com `kind` (`http`/`cve`), `url`,
    `fields` (campos permitidos), `ttl`, `rate_limit`, etc.
  - `DataSourceRegistry`: carrega o manifesto `sources.json` (`SOURCES_MANIFEST`).
  - `DataSourceService`: consulta com rate-limit, normaliza a resposta e **minimiza**
    para os campos declarados; cacheia no SQLite (`CveCache` p/ kind `cve`,
    `ExternalDataCache` nos demais) respeitando TTL.
- Expor via API: `GET /sources` e `POST /sources/{name}/query` (valida escopo).
- **Fallback determinístico**: fonte não configurada ou falha de rede retorna dados
  simulados estáveis (`status: "simulated"`), mantendo testes offline.

## Consequências

- Nova fonte é adicionada apenas editando `sources.json` — sem mudar código.
- Caches externos reutilizam os models migrados na Etapa 4; sem alteração de schema.
- Integração com agentes: `DataSourceService` é injetado no orquestrador como `PrivateAttr` do
  `GraphState` (`set_sources_service`), nos fluxos de run, stream, composição e CLI. Arquétipos
  consultam fontes via `_collect_sources` (rolam `available_sources()` e chamam `query`), sem
  conhecer fontes específicas; os resultados normalizados vão para o campo serializável
  `state.sources`. O serviço não é serializado/persistido.
- Minimização limita os campos retornados ao operacionalmente necessário.
