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


async def attempt_completion(
    system: str,
    user: str,
    *,
    devil_mode: bool = False,
    strategy: str = "priority",
) -> CompletionResult | None:
    """Call the gateway with a safe offline fallback.

    Returns ``None`` instead of raising when no API key is configured or every
    provider fails, so agents can degrade to deterministic behavior without
    failing the run. A fresh router is created and closed per call to avoid
    leaking the shared async client across graph nodes.
    """
    router = LLMRouter()
    try:
        return await router.complete(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ],
            devil_mode=devil_mode,
            strategy=strategy,
        )
    except (LLMError, ValueError):
        return None
    finally:
        await router.close()
