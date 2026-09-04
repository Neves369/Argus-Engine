"""In-process prefix cache for LLM completions (Etapa 3).

Caches a full ``CompletionResult`` keyed by the exact (provider, model,
messages, temperature, max_tokens) tuple that produced it. Repeated calls with
an identical prompt — common across a graph run, e.g. several archetypes
sharing the same short context, or a retried node — are served from cache
instead of paying for and waiting on another round trip.

This is a "prefix" cache in the sense the roadmap describes it (cache keyed by
the full request prompt), not a token-level KV-cache — that lives in the
provider's infrastructure, not here. Entries expire after ``ttl_seconds`` so a
long-lived process doesn't serve stale completions indefinitely.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

from app.llm.types import ChatMessage, CompletionResult, TokenUsage


def _cache_key(
    provider: str,
    model: str,
    messages: list[ChatMessage],
    temperature: float,
    max_tokens: int | None,
) -> str:
    payload = {
        "provider": provider,
        "model": model,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class _Entry:
    result: CompletionResult
    expires_at: float


class PrefixCache:
    """A small TTL cache for identical-prompt LLM completions.

    Not thread-safe beyond the GIL's dict-op atomicity, which is sufficient
    for this single-process async application (no true parallel node
    execution yet — see ROADMAP Etapa 1).
    """

    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, _Entry] = {}

    def get(
        self,
        provider: str,
        model: str,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
    ) -> CompletionResult | None:
        key = _cache_key(provider, model, messages, temperature, max_tokens)
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expires_at < time.monotonic():
            del self._store[key]
            return None
        # Return a copy so callers mutating `.strategy`/`.decision` in place
        # (see LLMRouter.complete) never corrupt the cached entry.
        cached = entry.result
        return CompletionResult(
            provider=cached.provider,
            model=cached.model,
            content=cached.content,
            usage=TokenUsage(**vars(cached.usage)),
            strategy=cached.strategy,
            decision=dict(cached.decision),
        )

    def set(
        self,
        provider: str,
        model: str,
        messages: list[ChatMessage],
        temperature: float,
        max_tokens: int | None,
        result: CompletionResult,
    ) -> None:
        key = _cache_key(provider, model, messages, temperature, max_tokens)
        self._store[key] = _Entry(result=result, expires_at=time.monotonic() + self.ttl_seconds)

    def clear(self) -> None:
        self._store.clear()

    def __len__(self) -> int:
        return len(self._store)


#: Process-wide cache instance. Deliberately module-level (not per-router):
#: `LLMRouter` instances are created fresh per call (see `attempt_completion`),
#: so a per-instance cache would never hit.
prefix_cache = PrefixCache()
