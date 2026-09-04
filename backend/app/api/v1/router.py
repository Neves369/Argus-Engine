from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import require_auth
from app.api.v1 import (
    archetypes,
    auth,
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

# Auth endpoints stay open (login/logout/me).
api_router.include_router(auth.router)

# Every other router requires the operator session cookie.
api_router.include_router(targets.router, dependencies=[Depends(require_auth)])
api_router.include_router(runs.router, dependencies=[Depends(require_auth)])
api_router.include_router(findings.router, dependencies=[Depends(require_auth)])
api_router.include_router(tools.router, dependencies=[Depends(require_auth)])
api_router.include_router(sources.router, dependencies=[Depends(require_auth)])
api_router.include_router(compositions.router, dependencies=[Depends(require_auth)])
api_router.include_router(dashboard.router, dependencies=[Depends(require_auth)])
api_router.include_router(archetypes.router, dependencies=[Depends(require_auth)])
api_router.include_router(providers.router, dependencies=[Depends(require_auth)])
