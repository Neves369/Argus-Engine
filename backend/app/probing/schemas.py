from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProbePriority = Literal["P0", "P1", "P2", "P3"]
ProbeSeverity = Literal["info", "low", "medium", "high", "critical"]


class Precondition(BaseModel):
    """Lead observacional que ativa a política (sempre derivado do scan)."""

    lead: Literal[
        "reflection",
        "verbose_error",
        "injection",
        "upload",
        "csrf",
        "redirect",
        "authn",
        "api",
    ]
    #: Matcher opcional sobre o título/categoria do finding de origem.
    title_contains: str | None = None
    category_contains: str | None = None


class AllowedProbe(BaseModel):
    """Ação mínima permitida: somente leitura e dentro dos controles do scan."""

    tool: str = "http_request"
    method: Literal["GET", "POST"] = "GET"
    max_per_endpoint: int = 1
    respect_robots: bool = True


class SignalRule(BaseModel):
    """Sinal determinístico avaliado contra a resposta fresca do probe.

    A semântica de cada ``kind`` é implementada em ``app/probing/engine.py``;
    o catálogo declara *o que observar*, nunca payloads ou passos de ataque.
    """

    kind: Literal[
        "body_contains",
        "body_none_of",
        "status_in",
        "reflects_param",
        "redirect_external",
        "missing_sensitive_field",
        "file_input_without_accept",
        "login_differential",
        "json_response",
        "json_has_array",
        "json_contains",
    ]
    value: str | int | list[str] | list[int] | None = None


class Reporting(BaseModel):
    """Como um sinal positivo vira finding na seção Comportamento."""

    title_template: str
    remediation: str
    references: list[str] = Field(default_factory=list)
    confidence: float = 0.6


class ProbePolicy(BaseModel):
    """Uma política de probe versionada (Etapa M6) — sem payload, só sinais."""

    id: str
    version: str
    name: str
    priority: ProbePriority
    class_label: str
    description: str
    precondition: Precondition
    allowed_probe: AllowedProbe
    positive_signal: list[SignalRule] = Field(default_factory=list)
    negative_signal: list[SignalRule] = Field(default_factory=list)
    candidate_severity: ProbeSeverity
    requires_hitl: bool = True
    default_enabled: bool = True
    reporting: Reporting