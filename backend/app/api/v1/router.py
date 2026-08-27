from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import runs, targets

api_router = APIRouter()
api_router.include_router(targets.router)
api_router.include_router(runs.router)
