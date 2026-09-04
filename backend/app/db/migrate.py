from __future__ import annotations

import asyncio
from pathlib import Path

from alembic.config import Config

from alembic import command

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


def _config() -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    cfg.set_main_option("prepend_sys_path", ".")
    return cfg


def upgrade_sync(revision: str = "head") -> None:
    """Apply migrations synchronously (used from a non-async context)."""
    command.upgrade(_config(), revision)


async def run_migrations(revision: str = "head") -> None:
    """Apply migrations from within the async application.

    ``alembic env.py`` runs its own event loop, so this is delegated to an
    executor thread to avoid ``asyncio.run()`` inside a running loop.
    """
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, upgrade_sync, revision)
