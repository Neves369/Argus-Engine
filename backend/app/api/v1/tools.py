from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.agents import get_archetype
from app.core.config import get_settings
from app.core.security import is_devil_mode_enabled, validate_scope
from app.tools.executor import ToolExecutionError, ToolExecutor
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolRead(BaseModel):
    name: str
    description: str
    kind: str
    destructive: bool


class ToolInvoke(BaseModel):
    params: dict[str, Any] = Field(default_factory=dict)
    target: str | None = None
    devil_mode: bool = False
    agent: str | None = None


_registry = ToolRegistry()
_registry.load(get_settings().tools_manifest)
_executor = ToolExecutor(_registry)


@router.get("", response_model=list[ToolRead])
async def list_tools() -> list[ToolRead]:
    return [
        ToolRead(
            name=spec.name,
            description=spec.description,
            kind=spec.kind,
            destructive=spec.destructive,
        )
        for name in _registry.available_tools()
        for spec in [_registry.get_tool(name)]
    ]


@router.post("/{name}/invoke")
async def invoke_tool(name: str, payload: ToolInvoke) -> dict[str, Any]:
    if payload.target is not None:
        try:
            validate_scope(payload.target)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        tool = _registry.get_tool(name)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    if payload.agent is not None:
        try:
            archetype = get_archetype(payload.agent)
        except KeyError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
            ) from exc
        if not _registry.authorize(tool, archetype.allowed_tools):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Archetype {payload.agent} is not allowed to use {name}",
            )

    devil_enabled = is_devil_mode_enabled(payload.devil_mode)

    try:
        return await _executor.execute(name, payload.params, devil_mode=devil_enabled)
    except ToolExecutionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
