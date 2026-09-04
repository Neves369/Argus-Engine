from __future__ import annotations

import asyncio
import json
import logging
import sys
from io import StringIO

import pytest

from app.core.config import get_settings
from app.core.logging import JsonFormatter
from app.core.secrets import has_secret, redact, scan
from app.tools import ToolExecutionError, ToolExecutor, ToolRegistry, ToolSpec
from app.tools.spec import ToolKind


def _make_registry(*specs: ToolSpec) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in specs:
        registry.register(spec)
    return registry


# --- app.core.secrets ---------------------------------------------------


@pytest.mark.parametrize(
    "text,label",
    [
        ("AKIAABCDEFGHIJKLMNOP", "AWS_ACCESS_KEY_ID"),
        ("ghp_" + "a" * 40, "GITHUB_TOKEN"),
        ("xoxb-1234567890-abcdefgh", "SLACK_TOKEN"),
        (
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PYb4XPMKp",
            "JWT",
        ),
        ("Authorization: Bearer abcdefghijklmnopqrstuvwxyz0123456789", "BEARER_TOKEN"),
        ("api_key = 'sk-abcdefghijklmnop'", "GENERIC_ASSIGNMENT"),
        ("-----BEGIN RSA PRIVATE KEY-----\nMIIB...\n-----END RSA PRIVATE KEY-----", "PRIVATE_KEY"),
    ],
)
def test_scan_detects_known_secret_shapes(text: str, label: str):
    assert label in scan(text)
    assert has_secret(text)


def test_scan_clean_text_has_no_findings():
    assert scan("just a normal sentence about the weather") == []
    assert not has_secret("target: example.com, confidence: 0.8")


def test_redact_removes_the_value_not_just_flags_it():
    text = "found leaked key: AKIAABCDEFGHIJKLMNOP in config"
    redacted = redact(text)
    assert "AKIAABCDEFGHIJKLMNOP" not in redacted
    assert "[REDACTED:AWS_ACCESS_KEY_ID]" in redacted


def test_redact_preserves_surrounding_text():
    text = "prefix AKIAABCDEFGHIJKLMNOP suffix"
    redacted = redact(text)
    assert redacted.startswith("prefix ")
    assert redacted.endswith(" suffix")


def test_redact_empty_string_is_noop():
    assert redact("") == ""


# --- logging redaction ----------------------------------------------------


def _format_record(logger_name: str, message: str, **extra) -> dict:
    record = logging.LogRecord(
        name=logger_name,
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg=message,
        args=(),
        exc_info=None,
    )
    for k, v in extra.items():
        setattr(record, k, v)
    return json.loads(JsonFormatter().format(record))


def test_json_formatter_redacts_message():
    payload = _format_record("test", "leaked token AKIAABCDEFGHIJKLMNOP in output")
    assert "AKIAABCDEFGHIJKLMNOP" not in payload["message"]
    assert "[REDACTED:AWS_ACCESS_KEY_ID]" in payload["message"]


def test_json_formatter_redacts_extra_fields_recursively():
    payload = _format_record(
        "test",
        "tool invoked",
        tool="danger",
        details={"stdout": "token: AKIAABCDEFGHIJKLMNOP", "nested": ["ghp_" + "b" * 40]},
    )
    assert "AKIAABCDEFGHIJKLMNOP" not in json.dumps(payload)
    assert "[REDACTED:AWS_ACCESS_KEY_ID]" in payload["details"]["stdout"]
    assert "[REDACTED:GITHUB_TOKEN]" in payload["details"]["nested"][0]


def test_json_formatter_passes_through_clean_fields():
    payload = _format_record("test", "run started", run_id=42, target="example.com")
    assert payload["run_id"] == 42
    assert payload["target"] == "example.com"


def test_setup_logging_end_to_end_redacts(monkeypatch):
    from app.core.logging import setup_logging

    stream = StringIO()
    setup_logging("INFO")
    root = logging.getLogger()
    # Swap stdout handler's stream so we can capture without touching fd 1.
    root.handlers[0].stream = stream

    logging.getLogger("etapa10").info(
        "credential found", extra={"raw": "api_key=abcdef1234567890"}
    )

    output = stream.getvalue()
    assert "abcdef1234567890" not in output
    assert "REDACTED" in output


# --- LLM client redaction (outbound prompt hardening) ----------------------


@pytest.mark.respx(base_url="https://api.groq.com")
def test_llm_client_redacts_secrets_before_sending(respx_mock, monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    from app.llm.client import UnifiedClient
    from app.llm.providers import get_provider
    from app.llm.types import ChatMessage

    respx_mock.post("/openai/v1/chat/completions").respond(
        json={
            "model": "llama-3.1-8b-instant",
            "choices": [{"message": {"role": "assistant", "content": "ack"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }
    )

    async def _run():
        client = UnifiedClient()
        try:
            provider = get_provider("groq")
            return await client.chat(
                provider,
                "llama-3.1-8b-instant",
                [ChatMessage(role="user", content="my key is AKIAABCDEFGHIJKLMNOP, help")],
            )
        finally:
            await client.close()

    asyncio.run(_run())

    sent_body = respx_mock.calls[0].request.content
    payload = json.loads(sent_body)
    sent_content = payload["messages"][0]["content"]
    assert "AKIAABCDEFGHIJKLMNOP" not in sent_content
    assert "[REDACTED:AWS_ACCESS_KEY_ID]" in sent_content


# --- Tool subprocess hardening ---------------------------------------------


def test_cli_timeout_kills_the_process():
    spec = ToolSpec(
        name="hang",
        kind=ToolKind.CLI,
        command=sys.executable,
        timeout=0.2,
    )
    registry = _make_registry(spec)

    async def _run() -> None:
        executor = ToolExecutor(registry)
        with pytest.raises(ToolExecutionError, match="timed out"):
            await executor.execute("hang", {"args": ["-c", "import time; time.sleep(30)"]})

    asyncio.run(_run())


def test_cli_output_is_truncated(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "tool_subprocess_max_output_bytes", 10)

    spec = ToolSpec(name="loud", kind=ToolKind.CLI, command=sys.executable, timeout=10.0)
    registry = _make_registry(spec)

    async def _run() -> dict:
        executor = ToolExecutor(registry)
        return await executor.execute("loud", {"args": ["-c", "print('x' * 1000)"]})

    result = asyncio.run(_run())
    assert result["stdout_truncated"] is True
    assert len(result["stdout"]) < 1000
    assert result["stdout"].endswith("...[truncated]")


def test_cli_output_not_flagged_when_within_limit():
    spec = ToolSpec(name="quiet", kind=ToolKind.CLI, command=sys.executable, timeout=10.0)
    registry = _make_registry(spec)

    async def _run() -> dict:
        executor = ToolExecutor(registry)
        return await executor.execute("quiet", {"args": ["-c", "print('ok')"]})

    result = asyncio.run(_run())
    assert result["stdout"] == "ok"
    assert result["stdout_truncated"] is False
    assert result["stderr_truncated"] is False


def test_cli_memory_limit_is_enforced():
    """A child that tries to allocate far beyond the configured cap should die,
    proving the rlimit was actually applied — not just accepted as config."""
    settings = get_settings()
    original = settings.tool_subprocess_memory_limit_mb
    settings.tool_subprocess_memory_limit_mb = 64  # tight cap for this test

    spec = ToolSpec(name="hog", kind=ToolKind.CLI, command=sys.executable, timeout=10.0)
    registry = _make_registry(spec)

    # Try to allocate ~500MB, well beyond the 64MB cap.
    script = "x = bytearray(500 * 1024 * 1024); print('should not get here')"

    async def _run() -> dict:
        executor = ToolExecutor(registry)
        return await executor.execute("hog", {"args": ["-c", script]})

    try:
        result = asyncio.run(_run())
        assert result["returncode"] != 0
        assert "should not get here" not in result["stdout"]
    finally:
        settings.tool_subprocess_memory_limit_mb = original
