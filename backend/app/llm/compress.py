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
from typing import Any

from app.llm.types import ChatMessage

_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_SPACES = re.compile(r"[ \t]+\n")

_TRUNCATION_MARKER = "\n...[compressed: {n} chars omitted]...\n"

# Palavras de enchimento removidas no modo Caveman. São artigos, conjunções e
# marcadores de cortesia que carregam pouca ou nenhuma intenção — seguros de
# descartar sem mudar o significado da instrução.
_CAVEMAN_DROP = re.compile(
    r"\b(a|an|the|and|or|but|if|then|of|to|for|with|that|this|these|those|"
    r"please|kindly|could you|would you|i would like you to|we need you to|"
    r"let's|let us|just|simply|basically|actually|really|very|somewhat|maybe|"
    r"note that|keep in mind|as a reminder|sure|okay|ok|alright)\b",
    re.IGNORECASE,
)
_CAVEMAN_SPACE = re.compile(r"\s{2,}")


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


def caveman_compress(text: str) -> str:
    """Strip filler words and collapse spacing to cut tokens (Etapa 7).

    Conservative on purpose: only drops low-signal function words and never
    touches code blocks, so the remaining instruction keeps its meaning. Runs
    after whitespace normalization.
    """
    text = normalize_whitespace(text)
    text = _CAVEMAN_DROP.sub(" ", text)
    text = _CAVEMAN_SPACE.sub(" ", text)
    return text.strip()


def compress_history(history: list[dict], *, keep_first: int = 1, keep_last: int = 8) -> list[dict]:
    """Trim the middle of a run's message history (Etapa 7).

    Keeps the first `keep_first` entries (usually the seed/context) and the
    last `keep_last`, dropping everything in between. Pure and deterministic —
    no LLM call — so it is safe to run offline between graph nodes.
    """
    if keep_first < 0:
        keep_first = 0
    if keep_last < 0:
        keep_last = 0
    if len(history) <= keep_first + keep_last:
        return list(history)
    head = history[:keep_first]
    tail = history[-keep_last:] if keep_last else []
    return head + tail


def compress_messages(
    messages: list[ChatMessage],
    *,
    max_chars: int | None = None,
    caveman: bool = False,
) -> list[ChatMessage]:
    """Return new `ChatMessage`s with whitespace normalized and length capped.

    Never mutates the input list/messages. `max_chars=None` (or <= 0) skips
    the length-capping pass; whitespace normalization always runs. `caveman=True`
    additionally strips filler words from each message body.
    """
    compressed: list[ChatMessage] = []
    for message in messages:
        content = normalize_whitespace(message.content)
        if caveman:
            content = caveman_compress(content)
        if max_chars:
            content = cap_length(content, max_chars)
        compressed.append(ChatMessage(role=message.role, content=content))
    return compressed


_EMPTY = (None, "", [], {})


def compact_tool_output(data: Any) -> Any:
    """Strip structural noise from tool/source output ("RTK ou equivalente", Etapa 7).

    Recursively drops keys/items whose value is ``None``, ``""``, ``[]`` or
    ``{}`` and collapses whitespace runs in strings — a field with no content
    carries no signal a model (or a human) needs, so removing it is pure
    token/byte savings, never a loss of information. Falsy-but-meaningful
    values (``0``, ``False``) are always kept.

    Applied to tool execution results (`app/tools/executor.py`) before they
    are stored or handed to an LLM prompt. Pure and deterministic — safe to
    run unconditionally when `settings.tool_output_compression` is enabled.
    """
    if isinstance(data, dict):
        compacted: dict[str, Any] = {}
        for key, value in data.items():
            value = compact_tool_output(value)
            if value in _EMPTY:
                continue
            compacted[key] = value
        return compacted
    if isinstance(data, list):
        items = [compact_tool_output(v) for v in data]
        return [v for v in items if v not in _EMPTY]
    if isinstance(data, str):
        return " ".join(data.split())
    return data
