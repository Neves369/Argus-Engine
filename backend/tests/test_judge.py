from __future__ import annotations

import asyncio

import pytest
import respx
from httpx import Response

from app.db.models import Finding
from app.services.false_positives import FalsePositiveBlacklist
from app.services.judge import JudgeVerdict, LLMJudge
from app.services.quality import QualityScorer, ValidationOutcome, ValidationPipeline


def _finding(**kwargs) -> Finding:
    defaults: dict = {"title": "test", "description": "desc", "confidence": 0.8}
    defaults.update(kwargs)
    return Finding(**defaults)


def _verdict_response(content: str, model: str = "llama-3.1-8b-instant") -> Response:
    return Response(
        200,
        json={
            "model": model,
            "choices": [{"message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        },
    )


_GROQ = "https://api.groq.com/openai/v1/chat/completions"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _fake_api_keys(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-groq")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-openrouter")


# ---- LLMJudge unit ----

@respx.mock
def test_judge_parses_verdict():
    respx.post(_GROQ).mock(
        return_value=_verdict_response('{"outcome": "validate", "reason": "clear signal"}')
    )
    verdict = _run(LLMJudge().judge(_finding(), evidence_count=1))
    assert verdict is not None
    assert verdict.outcome is ValidationOutcome.VALIDATE
    assert verdict.reason == "clear signal"
    assert verdict.tokens == 150
    assert verdict.provider == "groq"


@respx.mock
def test_judge_parses_fenced_json():
    respx.post(_GROQ).mock(
        return_value=_verdict_response(
            '```json\n{"outcome": "false_positive", "reason": "noise"}\n```'
        )
    )
    verdict = _run(LLMJudge().judge(_finding(), evidence_count=1))
    assert verdict is not None
    assert verdict.outcome is ValidationOutcome.FALSE_POSITIVE


@respx.mock
def test_judge_malformed_json_returns_none():
    respx.post(_GROQ).mock(return_value=_verdict_response("not json at all"))
    assert _run(LLMJudge().judge(_finding(), evidence_count=1)) is None


@respx.mock
def test_judge_invalid_outcome_returns_none():
    respx.post(_GROQ).mock(
        return_value=_verdict_response('{"outcome": "maybe", "reason": "?"}')
    )
    assert _run(LLMJudge().judge(_finding(), evidence_count=1)) is None


def test_judge_without_api_key_returns_none(monkeypatch):
    for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    assert _run(LLMJudge().judge(_finding(), evidence_count=1)) is None


@respx.mock
def test_judge_provider_error_returns_none():
    respx.post(_GROQ).mock(return_value=Response(500, text="boom"))
    respx.post("https://api.openai.com/v1/chat/completions").mock(
        return_value=Response(500, text="boom")
    )
    assert _run(LLMJudge().judge(_finding(), evidence_count=1)) is None


# ---- Pipeline with judge ----

class _FakeJudge:
    def __init__(self, verdict: JudgeVerdict | None):
        self._verdict = verdict
        self.calls = 0

    async def judge(self, finding, evidence_count):
        self.calls += 1
        return self._verdict


def _pipeline(judge):
    return ValidationPipeline(
        QualityScorer(),
        FalsePositiveBlacklist([]),
        threshold=0.6,
        judge=judge,
    )


def test_pipeline_uses_judge_when_available():
    verdict = JudgeVerdict(ValidationOutcome.FALSE_POSITIVE, "llm sees fp")
    judge = _FakeJudge(verdict)
    outcome, got = _run(_pipeline(judge).validate_with_judge(_finding(confidence=0.9), 1))
    assert judge.calls == 1
    assert outcome is ValidationOutcome.FALSE_POSITIVE
    assert got is verdict


def test_pipeline_falls_back_offline_without_judge():
    pipeline = ValidationPipeline(QualityScorer(), FalsePositiveBlacklist([]), threshold=0.6)
    outcome, got = _run(pipeline.validate_with_judge(_finding(confidence=0.9), 1))
    assert outcome is ValidationOutcome.VALIDATE
    assert got is None


def test_pipeline_judge_none_falls_back_to_rules():
    judge = _FakeJudge(None)
    outcome, got = _run(_pipeline(judge).validate_with_judge(_finding(confidence=0.9), 1))
    assert outcome is ValidationOutcome.VALIDATE
    assert got is None


def test_pipeline_high_severity_is_hard_stop():
    judge = _FakeJudge(JudgeVerdict(ValidationOutcome.VALIDATE, "llm says ok"))
    outcome, _ = _run(
        _pipeline(judge).validate_with_judge(_finding(confidence=0.9, severity="critical"), 2)
    )
    assert judge.calls == 0
    assert outcome is ValidationOutcome.NEEDS_REVIEW


def test_pipeline_blacklist_is_hard_stop():
    blacklist = FalsePositiveBlacklist(["known false positive"])
    judge = _FakeJudge(JudgeVerdict(ValidationOutcome.VALIDATE, "llm says ok"))
    pipeline = ValidationPipeline(QualityScorer(), blacklist, threshold=0.6, judge=judge)
    outcome, _ = _run(
        pipeline.validate_with_judge(_finding(title="known false positive"), 5)
    )
    assert judge.calls == 0
    assert outcome is ValidationOutcome.FALSE_POSITIVE


def test_pipeline_missing_evidence_is_hard_stop():
    judge = _FakeJudge(JudgeVerdict(ValidationOutcome.VALIDATE, "llm says ok"))
    outcome, _ = _run(_pipeline(judge).validate_with_judge(_finding(confidence=0.9), 0))
    assert judge.calls == 0
    assert outcome is ValidationOutcome.NEEDS_REVIEW


# ---- Endpoint integration ----

def _make_candidate(client, run_id):
    findings = client.get(f"/api/v1/runs/{run_id}/findings").json()
    return findings[-1]["id"]


def test_validate_endpoint_applies_judge(client):
    run = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    run_id = run.json()["id"]
    finding_id = _make_candidate(client, run_id)
    client.post(
        f"/api/v1/findings/{finding_id}/evidence",
        files={"file": ("r.txt", b"evidence", "text/plain")},
    )

    with respx.mock:
        respx.post(_GROQ).mock(
            return_value=_verdict_response('{"outcome": "validate", "reason": "ok"}')
        )
        response = client.post(f"/api/v1/findings/{finding_id}/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validated"
    assert body["meta"]["judge"]["outcome"] == "validate"
    assert body["meta"]["judge"]["model"] == "llama-3.1-8b-instant"


def test_validate_endpoint_falls_back_without_api_key(client, monkeypatch):
    run = client.post("/api/v1/runs", json={"target": {"name": "example.com"}})
    run_id = run.json()["id"]
    finding_id = _make_candidate(client, run_id)
    client.post(
        f"/api/v1/findings/{finding_id}/evidence",
        files={"file": ("r.txt", b"evidence", "text/plain")},
    )

    for key in ("GROQ_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    response = client.post(f"/api/v1/findings/{finding_id}/validate")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "validated"
    assert "judge" not in (body["meta"] or {})
