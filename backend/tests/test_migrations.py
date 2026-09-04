from __future__ import annotations

import sqlite3

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url

import app.db.models  # noqa: F401  (register models on Base.metadata)
from app.core.config import get_settings
from app.db.base import Base
from app.db.models.cve_cache import CveCache
from app.db.models.external_data_cache import ExternalDataCache
from app.db.models.session_model import Session
from app.db.session import async_session_factory


def test_lifespan_applies_migrations(client) -> None:
    """The app startup replaces create_all with alembic upgrade head."""
    url = get_settings().database_url  # sqlite+aiosqlite:///./data/test.db
    path = make_url(url).database
    con = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "runs" in tables
        assert "sessions" in tables
        assert "cve_cache" in tables
        assert "external_data_cache" in tables
        assert "alembic_version" in tables
    finally:
        con.close()


def test_models_in_sync_with_migrations(client) -> None:
    """No pending schema changes between the models and the latest migration."""
    url = get_settings().database_url
    path = make_url(url).database
    sync_engine = create_engine(f"sqlite:///{path}")
    with sync_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        diff = compare_metadata(ctx, Base.metadata)
    assert not diff, f"Models divergem da migração: {diff}"


def test_new_models_crud(client) -> None:
    """Session / CveCache / ExternalDataCache are usable after upgrade head."""

    async def _run() -> None:
        async with async_session_factory() as session:
            s = Session(name="engagement-alphasquad", status="open")
            cve = CveCache(cve_id="CVE-2024-0001", data={"cvss": 9.8}, ttl=3600)
            ext = ExternalDataCache(source="nvd", key="CVE-2024-0001", data={"desc": "x"})
            session.add_all([s, cve, ext])
            await session.commit()

            session_id = s.id
            cve_id_row = cve.id

        async with async_session_factory() as session:
            got = await session.get(Session, session_id)
            assert got is not None and got.name == "engagement-alphasquad"
            got_cve = await session.get(CveCache, cve_id_row)
            assert got_cve is not None and got_cve.data["cvss"] == 9.8
            rows = (await session.execute(select(ExternalDataCache))).scalars().all()
            assert len(rows) == 1

    import asyncio

    asyncio.run(_run())
