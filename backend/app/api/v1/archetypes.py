from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.agents import available_archetypes, get_archetype

router = APIRouter(prefix="/archetypes", tags=["archetypes"])


class ArchetypeRead(BaseModel):
    key: str
    name: str
    role: str
    model_tier: str
    allowed_tools: tuple[str, ...]


@router.get("", response_model=list[ArchetypeRead])
async def list_archetypes() -> list[ArchetypeRead]:
    archetypes = []
    for key in available_archetypes():
        agent = get_archetype(key)
        archetypes.append(
            ArchetypeRead(
                key=agent.key,
                name=agent.name,
                role=agent.role,
                model_tier=agent.model_tier,
                allowed_tools=agent.allowed_tools,
            )
        )
    return archetypes


@router.get("/{key}/schema")
async def get_archetype_schema(key: str) -> dict[str, Any]:
    """The mandatory output JSON Schema for this archetype's history entry (Etapa 2)."""
    try:
        agent = get_archetype(key)
    except KeyError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return agent.output_json_schema()
