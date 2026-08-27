from __future__ import annotations

from app.agents.base import BaseArchetype
from app.agents.builtin import (
    ChariotAgent,
    EmperorAgent,
    FoolAgent,
    HermitAgent,
    JusticeAgent,
    MagicianAgent,
)

_REGISTRY: dict[str, type[BaseArchetype]] = {
    EmperorAgent.key: EmperorAgent,
    HermitAgent.key: HermitAgent,
    FoolAgent.key: FoolAgent,
    JusticeAgent.key: JusticeAgent,
    ChariotAgent.key: ChariotAgent,
    MagicianAgent.key: MagicianAgent,
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
