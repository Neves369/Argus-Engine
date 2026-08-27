from __future__ import annotations

from abc import ABC, abstractmethod

from app.orchestration.state import GraphState


class BaseArchetype(ABC):
    """Contract shared by all agent archetypes.

    Each concrete archetype declares its role, preferred model tier and allowed tools,
    and implements `run()` which returns a partial GraphState update.
    """

    key: str = "base"
    name: str = "Base"
    role: str = "generic"
    model_tier: str = "cheap"
    allowed_tools: tuple[str, ...] = ()

    def system_prompt(self) -> str:
        return (
            f"You are {self.name}, the {self.role} archetype. "
            "Operate only within the authorized scope. Be concise."
        )

    @abstractmethod
    async def run(self, state: GraphState) -> dict:
        """Execute the archetype's task and return a partial state update."""
        raise NotImplementedError
