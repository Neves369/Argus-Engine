from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.security import validate_scope
from app.sources.registry import DataSourceRegistry
from app.sources.service import DataSourceError, DataSourceService

router = APIRouter(prefix="/sources", tags=["sources"])


class SourceRead(BaseModel):
    name: str
    description: str
    kind: str
    query_param: str
    target_kind: str


class SourceQuery(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None


_registry = DataSourceRegistry(get_settings().sources_manifest)
_service = DataSourceService(_registry)


@router.get("", response_model=list[SourceRead])
async def list_sources() -> list[SourceRead]:
    return [
        SourceRead(
            name=source.name,
            description=source.description,
            kind=source.kind,
            query_param=source.query_param,
            target_kind=source.target_kind,
        )
        for source in (_registry.get_source(name) for name in _registry.available_sources())
    ]


@router.post("/{name}/query")
async def query_source(name: str, payload: SourceQuery) -> dict[str, Any]:
    if payload.target is not None:
        try:
            validate_scope(payload.target)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    if not _registry.has_source(name):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown source: {name}"
        )

    try:
        return await _service.query(name, payload.params)
    except DataSourceError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
