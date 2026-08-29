from __future__ import annotations

from app.core.config import get_settings
from app.db.models import ApiUsage
from app.db.session import async_session_factory
from app.llm.cache import prefix_cache
from app.llm.client import LLMError, UnifiedClient
from app.llm.providers import get_provider, is_provider_enabled
from app.llm.types import ChatMessage, CompletionResult

#: Strategies that keep the pool in the order declared in settings.
_DECLARED_ORDER_STRATEGIES = {"priority", "fallback"}


def _combo_cost(combo: tuple[str, str]) -> float:
    """Estimated per-token price of a (provider, model) combo (price_in + price_out).

    Used only to *order* candidates for cost-aware strategies — the actual cost
    charged is still computed per-call from real token usage in ``client.py``.
    """
    provider_name, _ = combo
    try:
        provider = get_provider(provider_name)
    except KeyError:
        return float("inf")
    return provider.price_in + provider.price_out


async def _record_usage(result: CompletionResult) -> None:
    """Persiste uma linha ApiUsage para uma chamada LLM real (não-cache).

    Best-effort: falhas de gravação nunca derrubam a chamada LLM. O `run_id`
    fica nulo porque o gateway é usado fora de um run específico (agents e judge),
    mas a agregação por provider já funciona com base no provedor/modelo.
    """
    try:
        async with async_session_factory() as db:
            db.add(
                ApiUsage(
                    run_id=None,
                    provider=result.provider,
                    model=result.model,
                    prompt_tokens=result.usage.prompt_tokens,
                    completion_tokens=result.usage.completion_tokens,
                    cost=result.usage.cost,
                )
            )
            await db.commit()
    except Exception:
        pass


class LLMRouter:
    """Routes completions across providers/models, respecting execution mode.

    Mode routing: `devil_mode=True` uses the execution pool (unrestricted
    models); otherwise the judgment pool (fixed models). Within a pool, the
    ``strategy`` decides the *order* candidates are tried in; on any provider
    error `complete()` always degrades gracefully to the next candidate in
    that order, regardless of strategy.

    - ``priority`` / ``fallback``: try the pool in the order declared in
      settings (``EXECUTION_MODELS`` / ``JUDGMENT_MODELS``).
    - ``cost-optimized``: try the cheapest combo first, ranked by
      ``price_in + price_out`` (ties keep declared order — stable sort).
    - ``auto``: judgment calls are frequent/low-stakes, so they route
      cost-optimized; execution calls (``devil_mode=True``) keep declared
      priority order, since capability matters more than price there.

    Every call also goes through two cost-saving layers, both configurable
    via settings and transparent to callers:

    - **Prefix cache** (``app/llm/cache.py``): an identical
      (provider, model, messages, temperature, max_tokens) request served
      from memory skips the network entirely. ``result.decision["cache_hit"]``
      tells callers whether this particular result was cached.
    - **Prompt compression** (``app/llm/compress.py``, applied in
      ``UnifiedClient.chat``): whitespace normalization always runs; messages
      longer than ``settings.llm_max_prompt_chars`` are capped (head+tail
      kept) before being sent.
    """

    def __init__(self, client: UnifiedClient | None = None) -> None:
        self.client = client or UnifiedClient()

    def route_for_mode(
        self, devil_mode: bool, strategy: str = "priority"
    ) -> list[tuple[str, str]]:
        settings = get_settings()
        pool = settings.execution_models if devil_mode else settings.judgment_models

        combos: list[tuple[str, str]] = []
        for entry in pool:
            if "/" not in entry:
                continue
            provider, _, model = entry.partition("/")
            combos.append((provider, model))

        # Providers desabilitados via Settings/banco saem do pool de roteamento.
        combos = [c for c in combos if is_provider_enabled(c[0])]

        if strategy in _DECLARED_ORDER_STRATEGIES:
            return combos
        if strategy == "cost-optimized":
            return sorted(combos, key=_combo_cost)
        if strategy == "auto":
            return combos if devil_mode else sorted(combos, key=_combo_cost)
        raise ValueError(f"Unknown routing strategy: {strategy}")

    async def complete(
        self,
        messages: list[ChatMessage],
        *,
        devil_mode: bool = False,
        strategy: str = "priority",
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        combos = self.route_for_mode(devil_mode, strategy)
        if not combos:
            raise LLMError("No provider/model configured for this mode")

        cache_enabled = get_settings().llm_cache_enabled
        last_error: Exception | None = None
        for provider_name, model in combos:
            provider = get_provider(provider_name)

            cached = (
                prefix_cache.get(provider_name, model, messages, temperature, max_tokens)
                if cache_enabled
                else None
            )
            if cached is not None:
                result = cached
                result.decision["cache_hit"] = True
            else:
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
                result.decision["cache_hit"] = False
                if cache_enabled:
                    prefix_cache.set(
                        provider_name, model, messages, temperature, max_tokens, result
                    )
                await _record_usage(result)

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
    strategy: str | None = None,
) -> CompletionResult | None:
    """Call the gateway with a safe offline fallback.

    Returns ``None`` instead of raising when no API key is configured, every
    provider fails, or ``strategy`` is invalid, so agents can degrade to
    deterministic behavior without failing the run. A fresh router is created
    and closed per call to avoid leaking the shared async client across graph
    nodes. When ``strategy`` is omitted, the operator-configured default
    (``settings.llm_strategy``) is used.
    """
    resolved_strategy = strategy or get_settings().llm_strategy
    router = LLMRouter()
    try:
        return await router.complete(
            [
                ChatMessage(role="system", content=system),
                ChatMessage(role="user", content=user),
            ],
            devil_mode=devil_mode,
            strategy=resolved_strategy,
        )
    except (LLMError, ValueError):
        return None
    finally:
        await router.close()
