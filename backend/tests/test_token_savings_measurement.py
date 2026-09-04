"""Real, reproducible measurement of the Etapa 7 token-economy levers.

No tokenizer dependency is wired into this project, so character count is
used as the reduction proxy — clearly labeled as such, not presented as an
exact token count. For English/Portuguese technical text, ~4 chars/token is
a reasonable rule of thumb, so a character reduction is a fair (if
approximate) stand-in for a token reduction.

This file exists to replace the roadmap's previous vague "redução esperada"
with real, checked-in numbers from real sample inputs (an actual system
prompt used in production, a realistic third-party API response shape, and a
realistic multi-node run history) — and to lock those numbers in with
assertions so a future change to the compression functions that quietly
regresses the savings breaks CI instead of going unnoticed.
"""

from __future__ import annotations

from app.agents.builtin import HermitAgent
from app.llm.compress import (
    compact_tool_output,
    compress_history,
    compress_messages,
)
from app.llm.types import ChatMessage

# A real system prompt used in production (not a synthetic example).
_REAL_SYSTEM_PROMPT = HermitAgent().system_prompt()

# A realistic user-turn context, in the verbose/polite phrasing an operator
# might actually type (this is what Caveman mode is designed to compress —
# _context() itself is already terse and wouldn't show much movement).
_REAL_USER_CONTEXT = (
    "Please could you please analyze the target and then report any of the "
    "findings that you are able to see so far, and also please make sure "
    "that you consider the confidence level in order to decide whether or "
    "not you should continue investigating this particular target further."
)

# A realistic third-party API response shape: real APIs commonly return many
# optional fields as null/empty when not applicable (this mirrors the shape
# of an actual AbuseIPDB `check` response, not a synthetic worst case).
_REAL_TOOL_OUTPUT = {
    "data": {
        "ipAddress": "203.0.113.42",
        "isPublic": True,
        "ipVersion": 4,
        "isWhitelisted": None,
        "abuseConfidenceScore": 0,
        "countryCode": "US",
        "countryName": None,
        "usageType": "Data Center/Web Hosting/Transit",
        "isp": "Example Hosting Inc.",
        "domain": "example-hosting.com",
        "hostnames": [],
        "isTor": False,
        "totalReports": 0,
        "numDistinctUsers": 0,
        "lastReportedAt": None,
        "reports": [],
    }
}


def _char_count(value: object) -> int:
    return len(str(value))


def test_caveman_reduces_verbose_user_context_measurably():
    plain = compress_messages(
        [ChatMessage(role="user", content=_REAL_USER_CONTEXT)], caveman=False
    )[0].content
    caveman = compress_messages(
        [ChatMessage(role="user", content=_REAL_USER_CONTEXT)], caveman=True
    )[0].content

    before, after = _char_count(plain), _char_count(caveman)
    reduction_pct = round((1 - after / before) * 100, 1)

    # Real measured numbers as of this test (see docs/ROADMAP.md Etapa 7):
    # 276 chars -> 188 chars, ~32% reduction on verbose, filler-heavy input.
    assert before == 276
    assert after == 188
    assert reduction_pct >= 25.0


def test_caveman_barely_touches_already_terse_system_prompt():
    """Caveman is conservative by design — a prompt with little filler to
    begin with (like our own system prompts) shows small, not dramatic,
    savings. This is the honest complement to the test above: the lever
    helps most on verbose input, not on prompts we already wrote tersely."""
    plain = compress_messages(
        [ChatMessage(role="system", content=_REAL_SYSTEM_PROMPT)], caveman=False
    )[0].content
    caveman = compress_messages(
        [ChatMessage(role="system", content=_REAL_SYSTEM_PROMPT)], caveman=True
    )[0].content

    before, after = _char_count(plain), _char_count(caveman)
    assert after <= before
    # Single-digit percent — documents that this lever's real value is on
    # verbose/conversational text, not on prompts already written tight.
    reduction_pct = round((1 - after / before) * 100, 1)
    assert reduction_pct < 10.0


def test_compact_tool_output_reduces_realistic_api_response_measurably():
    import json

    before = json.dumps(_REAL_TOOL_OUTPUT)
    after = json.dumps(compact_tool_output(_REAL_TOOL_OUTPUT), separators=(",", ":"))

    before_len, after_len = len(before), len(after)
    reduction_pct = round((1 - after_len / before_len) * 100, 1)

    # Real measured numbers (see docs/ROADMAP.md Etapa 7): every null/empty
    # optional field AbuseIPDB returns when there's nothing to report is
    # dropped, plus JSON minification (no extra whitespace).
    assert before_len == 391
    assert after_len == 269
    assert reduction_pct >= 25.0
    # No real data lost: every non-empty value from the original survives.
    compacted = compact_tool_output(_REAL_TOOL_OUTPUT)
    assert compacted["data"]["ipAddress"] == "203.0.113.42"
    assert compacted["data"]["abuseConfidenceScore"] == 0  # falsy-but-real, kept
    assert compacted["data"]["isTor"] is False  # falsy-but-real, kept


def test_history_compression_reduces_context_on_a_realistic_long_run():
    # Realistic history entries — same shape _apply_llm actually produces.
    history = [
        {
            "agent": "hermit",
            "action": "simulate",
            "findings": i,
            "sources_consulted": 3,
            "reasoning": (
                "Consulted crt.sh, NVD and AbuseIPDB for the target; no high-"
                "confidence signal found in this pass, confidence raised "
                "incrementally pending further collection."
            ),
            "tokens": 180,
            "provider": "groq",
            "model": "llama-3.1-8b-instant",
        }
        for i in range(20)
    ]

    import json

    before_len = len(json.dumps(history))
    compressed = compress_history(history, keep_first=1, keep_last=8)
    after_len = len(json.dumps(compressed))

    reduction_pct = round((1 - after_len / before_len) * 100, 1)

    assert len(compressed) == 9  # 1 head + 8 tail, out of 20
    assert reduction_pct >= 50.0
