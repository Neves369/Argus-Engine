from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import findings, runs, targets, tools

api_router = APIRouter()
api_router.include_router(targets.router)
api_router.include_router(runs.router)
api_router.include_router(findings.router)
api_router.include_router(tools.router)
