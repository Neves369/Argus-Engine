from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url, echo=settings.debug, future=True)

# SQLite concurrency (Etapa 13, E2E): as pernas paralelas do Eremita
# (sweep de fontes + correlação + registro de uso LLM) abrem conexões
# separadas escrevendo no mesmo arquivo. No journal mode default
# (rollback), um único escritor bloquearia os demais e estouraria
# "database is locked" em vez de esperar. WAL + busy_timeout fazem as
# escritas concorrentes se serializarem com retry em vez de falhar.
if engine.dialect.name == "sqlite":


    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, _connection_record) -> None:  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session
