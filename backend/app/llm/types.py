from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cost: float = 0.0


@dataclass
class CompletionResult:
    provider: str
    model: str
    content: str
    usage: TokenUsage
    strategy: str = ""
    decision: dict[str, Any] = field(default_factory=dict)
