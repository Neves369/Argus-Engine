from __future__ import annotations

from app.core.config import get_settings
from app.llm.client import LLMError, UnifiedClient
from app.llm.providers import get_provider
from app.llm.types import ChatMessage, CompletionResult


class LLMRouter:
    """Routes completions across providers/models, respecting execution mode.

    Mode routing: `devil_mode=True` uses the execution pool (unrestricted
    models); otherwise the judgment pool (fixed models). The strategy loops
    over the ordered pool — priority uses the first available combo, fallback
    degrades gracefully to the next on any provider error.
    """

    def __init__(self, client: UnifiedClient | None = None) -> None:
        self.client = client or UnifiedClient()

    def route_for_mode(self, devil_mode: bool) -> list[tuple[str, str]]:
        settings = get_settings()
        pool = settings.execution_models if devil_mode else settings.judgment_models

        combos: list[tuple[str, str]] = []
        for entry in pool:
            if "/" not in entry:
                continue
            provider, _, model = entry.partition("/")
            combos.append((provider, model))
        return combos

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        devil_mode: bool = False,
        strategy: str = "priority",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        combos = self.route_for_mode(devil_mode)
        if not combos:
            raise LLMError("No provider/model configured for this mode")

        last_error: Exception | None = None
        for provider_name, model in combos:
            provider = get_provider(provider_name)
            try:
                result = await self.client.chat(
                    provider,
                    model,
                    messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
            except LLMError as exc:
                last_error = exc
                continue
            result.strategy = strategy
            result.decision["strategy"] = strategy
            result.decision["mode"] = "execute" if devil_mode else "judgment"
            return result

        raise LLMError(f"All providers failed (strategy={strategy})") from last_error

    async def close(self) -> None:
        await self.client.close()
