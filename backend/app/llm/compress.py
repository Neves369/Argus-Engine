"""Prompt compression for outbound LLM messages (Etapa 3).

Two independent, deliberately conservative passes:

1. Whitespace normalization — collapses runs of blank lines/spaces that add
   tokens without adding meaning (common when context strings are built by
   joining several ``f"...\\n"`` fragments, as ``BaseArchetype._context`` does).
2. Length capping — truncates any single message body that exceeds
   ``max_chars``, keeping the head and tail (where the actionable instruction
   usually lives) and dropping the middle. Archetype contexts today are a
   handful of short lines, so this is a safety net for future, larger
   payloads (e.g. tool output or long finding lists fed back into a prompt)
   rather than something that fires in current flows.
"""

from __future__ import annotations

import re

from app.llm.types import ChatMessage

_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")

_TRUNCATION_MARKER = "\n...[compressed: {n} chars omitted]...\n"


def normalize_whitespace(text: str) -> str:
    """Collapse redundant blank lines and trailing spaces without touching content."""
    text = _TRAILING_SPACES.sub("\n", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip("\n")


def cap_length(text: str, max_chars: int) -> str:
    """Keep head + tail of `text`, dropping the middle, if over `max_chars`."""
    if max_chars <= 0 or len(text) <= max_chars:
        return text
    # Reserve room for the marker itself; split remaining budget head/tail.
    omitted = len(text) - max_chars
    marker = _TRUNCATION_MARKER.format(n=omitted)
    budget = max(max_chars - len(marker), 0)
    head_len = budget // 2
    tail_len = budget - head_len
    if tail_len:
        return text[:head_len] + marker + text[-tail_len:]
    return text[:head_len] + marker


def compress_messages(
    messages: list[ChatMessage], *, max_chars: int | None = None
) -> list[ChatMessage]:
    """Return new `ChatMessage`s with whitespace normalized and length capped.

    Never mutates the input list/messages. `max_chars=None` (or <= 0) skips
    the length-capping pass; whitespace normalization always runs.
    """
    compressed: list[ChatMessage] = []
    for message in messages:
        content = normalize_whitespace(message.content)
        if max_chars:
            content = cap_length(content, max_chars)
        compressed.append(ChatMessage(role=message.role, content=content))
    return compressed
