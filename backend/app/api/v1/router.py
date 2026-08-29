from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    archetypes,
    compositions,
    dashboard,
    findings,
    providers,
    runs,
    sources,
    targets,
    tools,
)

api_router = APIRouter()
api_router.include_router(targets.router)
api_router.include_router(runs.router)
api_router.include_router(findings.router)
api_router.include_router(tools.router)
api_router.include_router(sources.router)
api_router.include_router(compositions.router)
api_router.include_router(dashboard.router)
api_router.include_router(archetypes.router)
api_router.include_router(providers.router)
