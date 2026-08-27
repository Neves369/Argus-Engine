from __future__ import annotations

from abc import ABC, abstractmethod

from app.llm.router import attempt_completion
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
            "Operate only within the authorized scope. Be concise. "
            "Return only a short, factual assessment — no techniques, no payloads."
        )

    def _context(self, state: GraphState) -> str:
        name = state.target.get("name", "unknown")
        return (
            f"Target: {name}\n"
            f"Findings: {len(state.findings)}\n"
            f"Evidence: {len(state.evidence)}\n"
            f"Confidence: {state.confidence:.2f}\n"
            f"Tokens used so far: {state.tokens_used}\n"
            f"Mode: {'execute' if state.devil_mode else 'simulate'}"
        )

    async def _attempt(self, state: GraphState, *, devil_mode: bool = False):
        """Try the LLM gateway; return ``None`` when the call is unavailable."""
        return await attempt_completion(
            self.system_prompt(), self._context(state), devil_mode=devil_mode
        )

    @abstractmethod
    async def run(self, state: GraphState) -> dict:
        """Execute the archetype's task and return a partial state update."""
        raise NotImplementedError
