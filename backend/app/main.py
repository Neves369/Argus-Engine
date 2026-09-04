from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import app.db.models  # noqa: F401  (register models on Base.metadata)
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.crypto import has_encryption
from app.core.logging import setup_logging
from app.core.policy import load_policy
from app.db.migrate import run_migrations
from app.db.session import engine
from app.schemas.health import Health
from app.schemas.policy import PolicyRead
from app.services.provider_config import _load_overrides_from_db

settings = get_settings()
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data").mkdir(parents=True, exist_ok=True)
    await run_migrations()
    if has_encryption():
        await _load_overrides_from_db()
    app.state.policy = load_policy()
    yield
    await engine.dispose()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", response_model=Health, tags=["health"])
async def health() -> Health:
    return Health(status="ok", app=settings.app_name)


@app.get("/policy", response_model=PolicyRead, tags=["policy"])
async def authorized_use_policy() -> PolicyRead:
    return load_policy()
