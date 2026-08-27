# ADR-0002 — Migrações de banco com Alembic no startup

**Status:** Aceito

## Contexto

O schema do banco (SQLite via `sqlite+aiosqlite`) era criado por
`Base.metadata.create_all` no `lifespan` da aplicação. Isso funciona em dev, mas não
oferece histórico de mudanças nem migrações incrementais para bancos existentes.
Com o schema estabilizando (7 models + novos `sessions`, `cve_cache`,
`external_data_cache`), a Etapa 4 do ROADMAP prevê introduzir Alembic.

## Decisão

- Introduzir Alembic com `env.py` **async** (SQLAlchemy 2.0 + aiosqlite), lendo a
  `DATABASE_URL` das settings (`app.core.config`).
- O `lifespan` do app substitui `create_all` por `alembic upgrade head`
  (via `app/db/migrate.py`), delegado a uma executor thread porque o `env.py`
  roda seu próprio event loop.
- Disponibilizar `make migrate` e `make revision` para uso manual.
- Migração inicial autogerada a partir de `Base.metadata` cobre os 10 models.

## Consequências

- Banco sempre no schema corrente ao subir a aplicação, com histórico versionado
  na tabela `alembic_version`.
- Bancos criados antes do Alembic (via `create_all`) precisam ser recriados ou
  "baselineados"; o banco dev `data/argus.db` é descartável.
- Testes passam a exercitar o fluxo real de migração (schema completo + sincronia
  entre models e migrações + CRUD dos models novos).
