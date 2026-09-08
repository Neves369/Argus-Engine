from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.llm.compress import llm_summarize_middle
from app.llm.types import CompletionResult, TokenUsage
from app.orchestration.graph import _provisioned
from app.orchestration.state import GraphState


def _history(n: int) -> list[dict]:
    return [
        {"role": "user" if i % 2 else "assistant", "content": f"msg {i}"}
        for i in range(n)
    ]


def _fake_result(content: str) -> CompletionResult:
    return CompletionResult(
        provider="fake",
        model="fake-model",
        content=content,
        usage=TokenUsage(),
    )


def test_llm_summarize_middle_offline_falls_back_to_deterministic(monkeypatch):
    async def _offline(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.llm.router.attempt_completion", _offline)

    async def _run() -> tuple[list[dict], bool]:
        return await llm_summarize_middle(_history(12), keep_first=1, keep_last=8)

    result, summarized = asyncio.run(_run())
    assert summarized is False
    assert len(result) == 9
    assert result[0] == _history(12)[0]
    assert result[1:] == _history(12)[-8:]


def test_llm_summarize_middle_keeps_head_tail_and_adds_summary(monkeypatch):
    calls: list[str] = []

    async def _fake(_system: str, user: str) -> CompletionResult:
        calls.append(user)
        return _fake_result("portas 22 e 443 abertas; token de sessão vazado")

    monkeypatch.setattr("app.llm.router.attempt_completion", _fake)
    history = _history(12)

    async def _run() -> tuple[list[dict], bool]:
        return await llm_summarize_middle(history, keep_first=1, keep_last=8)

    result, summarized = asyncio.run(_run())
    assert summarized is True
    assert result[0] == history[0]
    assert result[-8:] == history[-8:]
    assert len(result) == 10
    assert "contexto intermediário resumido" in result[1]["content"]
    assert "portas 22 e 443" in result[1]["content"]
    assert any("msg 2" in c for c in calls)  # o meio (índices 1..3) vai pro resumo
    assert not any("msg 7" in c for c in calls)  # a cauda fica de fora


def test_llm_summarize_middle_small_history_is_noop(monkeypatch):
    called: list[int] = []

    async def _fake(*_args, **_kwargs) -> CompletionResult:
        called.append(1)
        return _fake_result("x")

    monkeypatch.setattr("app.llm.router.attempt_completion", _fake)
    history = _history(5)

    async def _run() -> tuple[list[dict], bool]:
        return await llm_summarize_middle(history, keep_first=1, keep_last=8)

    result, summarized = asyncio.run(_run())
    assert not called
    assert summarized is False
    assert result == history


def test_provisioned_summarizes_once_then_deterministic(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "history_compression", True)
    monkeypatch.setattr(settings, "history_llm_summary", True)
    monkeypatch.setattr(settings, "history_keep_last", 8)

    calls = {"summary": 0}

    async def _fake(_system: str, _user: str) -> CompletionResult:
        calls["summary"] += 1
        return _fake_result("resumo de teste")

    monkeypatch.setattr("app.llm.router.attempt_completion", _fake)

    async def _fn(_state: GraphState) -> dict:
        return {"node": "fake"}

    async def _run() -> None:
        provisioned = _provisioned(_fn, None)
        state = GraphState(history=_history(12))
        result = await provisioned(state)
        assert state.history_summary_done is True
        assert result["history_summary_done"] is True
        assert "contexto intermediário resumido" in state.history[1]["content"]
        assert calls["summary"] == 1

        state.history.extend(_history(2))  # volta a estourar o limiar
        await provisioned(state)
        assert calls["summary"] == 1  # não resume de novo — só determinístico
        assert state.history_summary_done is True
        assert len(state.history) == 9

    asyncio.run(_run())


def test_provisioned_marks_done_even_when_offline(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "history_compression", True)
    monkeypatch.setattr(settings, "history_llm_summary", True)

    async def _offline(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr("app.llm.router.attempt_completion", _offline)

    async def _fn(_state: GraphState) -> dict:
        return {"node": "fake"}

    async def _run() -> None:
        provisioned = _provisioned(_fn, None)
        state = GraphState(history=_history(12))
        result = await provisioned(state)
        assert result["history_summary_done"] is True
        assert state.history_summary_done is True
        assert len(state.history) == 9  # meio descartado (determinístico)

    asyncio.run(_run())