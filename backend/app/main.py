from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

import app.db.models  # noqa: F401  (register models on Base.metadata)
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.crypto import has_encryption
from app.core.logging import setup_logging
from app.core.policy import load_policy
from app.core.security import is_kill_switch_active
from app.db.migrate import run_migrations
from app.db.session import async_session_factory, engine
from app.metrics import (
    BUILD_INFO,
    METRICS_PATH,
    MetricsMiddleware,
    metrics_headers,
    metrics_response,
    set_kill_switch,
)
from app.schemas.health import Health
from app.schemas.policy import PolicyRead
from app.services.app_settings import load_ui_password_override_from_db
from app.services.provider_config import _load_overrides_from_db
from app.services.run_recovery import recover_stale_runs

settings = get_settings()
logger = logging.getLogger("argus")
setup_logging(settings.log_level)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path("data").mkdir(parents=True, exist_ok=True)
    await run_migrations()
    async with async_session_factory() as session:
        recovered = await recover_stale_runs(session)
        if recovered:
            logger.info("Recuperou %d run(s) órfão(s): %s", len(recovered), recovered)
    if has_encryption():
        await _load_overrides_from_db()
        await load_ui_password_override_from_db()
    app.state.policy = load_policy()
    BUILD_INFO.labels(settings.app_name).set(1)
    set_kill_switch(is_kill_switch_active())
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

app.add_middleware(MetricsMiddleware)

app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/health", response_model=Health, tags=["health"])
async def health() -> Health:
    return Health(status="ok", app=settings.app_name)


@app.get(METRICS_PATH, include_in_schema=False, tags=["metrics"])
async def metrics() -> Response:
    """Exposição de métricas no formato do Prometheus."""
    return Response(content=await metrics_response(), headers=metrics_headers())


@app.get("/policy", response_model=PolicyRead, tags=["policy"])
async def authorized_use_policy() -> PolicyRead:
    return load_policy()
