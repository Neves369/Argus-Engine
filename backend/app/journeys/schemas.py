from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

JourneyMethod = Literal["GET", "POST"]
JourneyPriority = Literal["P0", "P1", "P2", "P3"]
JourneySeverity = Literal["info", "low", "medium", "high", "critical"]

_JOURNEY_DEFAULT_STATUSES = [200, 201, 204]


class JourneyExpect(BaseModel):
    """Efeito esperado de um passo da jornada (regra determinística)."""

    #: Status aceitos como "efeito alcançado" para o passo.
    status_in: list[int] = Field(default_factory=lambda: list(_JOURNEY_DEFAULT_STATUSES))
    #: Substring que a resposta deve conter para o efeito valer.
    contains: str | None = None


class JourneyStep(BaseModel):
    """Um passo da jornada: requisição literal + efeito esperado.

    O Argus nunca inventa passo de jornada: cada ``path``/``body``/``expect``
    é declarado pelo operador no catálogo versionado (``policies/journeys/*.yaml``)
    e re-executado igual para anônimo e cada sessão autenticada, dentro dos
    controles (escopo/kill-switch/robots/rate-limit/teto de passos).
    """

    name: str
    method: JourneyMethod = "GET"
    path: str = "/"
    #: Body literal e estático para o passo (ex.: um formulário observado no
    #: crawl). Nunca credenciais reais — jornadas não fazem login por conta.
    body: dict[str, str] = Field(default_factory=dict)
    expect: JourneyExpect = Field(default_factory=JourneyExpect)


class JourneyReporting(BaseModel):
    """Como um passo com efeito dependente de sessão vira finding."""

    title_template: str
    remediation: str
    references: list[str] = Field(default_factory=list)
    confidence: float = 0.5


class Journey(BaseModel):
    """Uma jornada multi-step versionada (Etapa M7-P3) — só requisições legítimas."""

    id: str
    version: str
    name: str
    priority: JourneyPriority = "P0"
    description: str
    steps: list[JourneyStep] = Field(min_length=1)
    #: Re-executa a jornada também sem sessão (baseline anônimo para comparar
    #: acesso). Desligar roda só nas sessões autenticadas.
    run_anonymous: bool = True
    default_enabled: bool = True
    candidate_severity: JourneySeverity = "low"
    requires_hitl: bool = True
    reporting: JourneyReporting