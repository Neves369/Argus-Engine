from __future__ import annotations

import httpx

from app.core.config import get_settings
from app.core.secrets import redact
from app.llm.compress import compress_messages
from app.llm.providers import ProviderSpec
from app.llm.types import ChatMessage, CompletionResult, TokenUsage


class LLMError(RuntimeError):
    """Raised when a provider call fails or returns a malformed response."""


def _compute_cost(provider: ProviderSpec, prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        (prompt_tokens / 1_000_000) * provider.price_in
        + (completion_tokens / 1_000_000) * provider.price_out,
        6,
    )


class UnifiedClient:
    """OpenAI-compatible async client shared by all providers."""

    def __init__(self, timeout: float = 30.0) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._client.aclose()

    async def chat(
        self,
        provider: ProviderSpec,
        model: str,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> CompletionResult:
        settings = get_settings()
        max_chars = settings.llm_max_prompt_chars
        messages = compress_messages(
            messages, max_chars=max_chars, caveman=settings.caveman_prompts
        )
        # Hardening (Etapa 10): never forward a secret-shaped string to a
        # third-party provider, even if it slipped into a node's context.
        messages = [ChatMessage(role=m.role, content=redact(m.content)) for m in messages]

        url = f"{provider.base_url}/chat/completions"
        try:
            api_key = provider.api_key
        except ValueError as exc:
            # Chave ausente conta como falha do provider (o router cai no
            # próximo combo) — não um crash do run inteiro.
            raise LLMError(f"{provider.name}: missing API key") from exc
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": model,
            "messages": [m.__dict__ for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        try:
            response = await self._client.post(url, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            raise LLMError(f"{provider.name} request failed: {exc}") from exc

        if response.status_code >= 400:
            raise LLMError(
                f"{provider.name} returned {response.status_code}: {response.text[:200]}"
            )

        try:
            data = response.json()
            choice = data["choices"][0]
            usage = data.get("usage", {})
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"{provider.name} returned a malformed response") from exc

        content = choice["message"]["content"]
        prompt_tokens = int(usage.get("prompt_tokens", 0))
        completion_tokens = int(usage.get("completion_tokens", 0))
        total_tokens = int(usage.get("total_tokens", prompt_tokens + completion_tokens))
        resolved_model = data.get("model", model)

        return CompletionResult(
            provider=provider.name,
            model=resolved_model,
            content=content,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                cost=_compute_cost(provider, prompt_tokens, completion_tokens),
            ),
            decision={
                "provider": provider.name,
                "model": resolved_model,
            },
        )
