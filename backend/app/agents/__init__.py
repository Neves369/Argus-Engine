from __future__ import annotations

from app.agents.base import BaseArchetype
from app.agents.builtin import AnalystAgent, CollectorAgent, DirectorAgent

_REGISTRY: dict[str, type[BaseArchetype]] = {
    DirectorAgent.key: DirectorAgent,
    CollectorAgent.key: CollectorAgent,
    AnalystAgent.key: AnalystAgent,
}


def get_archetype(key: str) -> BaseArchetype:
    try:
        cls = _REGISTRY[key]
    except KeyError:
        raise KeyError(f"Unknown archetype: {key}") from None
    return cls()


def available_archetypes() -> list[str]:
    return list(_REGISTRY)


__all__ = ["BaseArchetype", "available_archetypes", "get_archetype"]
