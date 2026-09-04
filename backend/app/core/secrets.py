"""Secret scanning and redaction (Etapa 10 hardening).

Two independent uses of the same pattern set, wired in at different points:

1. **Logging** (`app/core/logging.py`): every field of every log record is
   redacted before being serialized, so a secret that ends up in a log
   message or an `extra={...}` value never reaches stdout/log aggregation.
2. **Outbound LLM prompts** (`app/llm/client.py`): message content is
   redacted before being sent to a third-party provider, so a credential
   surfaced during an investigation is never forwarded off-platform.

This is deliberately **not** wired into evidence storage: evidence is the
operator's own findings database, and a discovered credential is often
exactly what the finding *is* — redacting it there would destroy the
evidence. Secret handling for evidence is an operator/retention-policy
concern, not something this layer should silently rewrite.

Patterns are intentionally generic/heuristic (assignment-style `key = value`,
well-known token prefixes, PEM blocks) — good enough to catch the common
"a token ended up somewhere it shouldn't" case, not a substitute for a
dedicated secret-scanning product on the ones that matter most (e.g. inputs
before they enter version control).
"""

from __future__ import annotations

import re

# Each pattern replaces its match with ``[REDACTED:<label>]``. Order matters
# only in that more specific patterns are listed first, since a string could
# in principle satisfy more than one (each pass runs independently, so
# overlap just means more than one label could apply — harmless).
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "PRIVATE_KEY",
        re.compile(
            r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
            r"[\s\S]+?-----END (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"
        ),
    ),
    ("AWS_ACCESS_KEY_ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("GITHUB_TOKEN", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("SLACK_TOKEN", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    (
        "BEARER_TOKEN",
        re.compile(r"(?i)\bbearer\s+[A-Za-z0-9\-_.=]{20,}"),
    ),
    (
        "GENERIC_ASSIGNMENT",
        re.compile(
            r"(?i)\b(api[_-]?key|apikey|secret|token|password|passwd|pwd)"
            r"\s*[:=]\s*['\"]?[A-Za-z0-9/+_\-=]{8,}['\"]?"
        ),
    ),
)


def scan(text: str) -> list[str]:
    """Return the labels of secret-shaped substrings found in `text`.

    Never returns the matched value itself — only what *kind* of secret it
    looked like — so this is safe to call in contexts that then log the
    result (e.g. "redacted 2 secrets: API_KEY, JWT" is safe; the raw text
    is not).
    """
    found: list[str] = []
    for label, pattern in _PATTERNS:
        if pattern.search(text):
            found.append(label)
    return found


def redact(text: str) -> str:
    """Replace every secret-shaped substring in `text` with a labeled placeholder."""
    if not text:
        return text
    for label, pattern in _PATTERNS:
        text = pattern.sub(f"[REDACTED:{label}]", text)
    return text


def has_secret(text: str) -> bool:
    return bool(scan(text))
