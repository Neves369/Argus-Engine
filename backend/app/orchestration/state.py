from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, PrivateAttr, model_validator


class GraphState(BaseModel):
    """Shared, typed state passed between graph nodes.

    Serializable by design so a run can be persisted and resumed.
    """

    target: dict[str, Any] = Field(default_factory=dict)
    findings: list[dict[str, Any]] = Field(default_factory=list)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    trace: list[dict[str, Any]] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    scan: list[dict[str, Any]] = Field(default_factory=list)

    tokens_used: int = 0
    cost: float = 0.0

    #: Per-agent totals, keyed by archetype key (e.g. "hermit"). Only
    #: meaningful for archetypes that can loop (hermit/chariot via the
    #: supervisor) — a custom pipeline runs each archetype once, so its own
    #: total is just that single call's usage. See `budget_tokens_per_agent`
    #: in settings; o teto per-agente é respeitado pelo Imperador ao delegar
    #: (`EmperorAgent`), e o teto do run é aplicado em `route_after_worker` e
    #: no router do pipeline em `app.orchestration.graph`.
    tokens_by_agent: dict[str, int] = Field(default_factory=dict)
    cost_by_agent: dict[str, float] = Field(default_factory=dict)

    budget_tokens: int = 100_000
    budget_cost: float = 1.0

    confidence: float = 0.0
    stop_reason: str | None = None
    next_agent: str | None = None
    #: Profundidade do run (Etapa M3): ``quick`` = fontes + scan de superfície +
    #: Justiça leve; ``deep`` = autenticação → crawl de módulos → forms → probes
    #: do Carro → Justiça. Serializado (persiste em resume). Default seguro.
    depth: str = "quick"
    #: Allowlist de classes de probe do catálogo M6 (Etapa M6, guardrail 6.3).
    #: ``None`` → default seguro em ``probe_classes_default`` (P0 apenas).
    #: Serializado (persiste em resume); validação contra o catálogo é feita no
    #: motor (só libera classes existentes/versionadas).
    probe_classes: list[str] | None = None
    #: Jornadas multi-step liberadas (M7-P3), por id do catálogo. ``None`` →
    #: default em ``journey_classes_default``. Serializado (persiste em resume).
    journey_classes: list[str] | None = None
    #: Pacote de política aplicado (M10-P0): id do pacote + snapshot resolvido
    #: (depth/probe_classes/journey_classes/devil_mode + sha256) para auditoria
    #: e reprodução. Serializado (persiste em resume e aparece no relatório).
    policy_package: str | None = None
    policy_resolved: dict[str, Any] | None = None
    #: Preset Tarot aplicado (M10-P3): id do preset + snapshot resolvido
    #: (archetypes/policy_package + sha256) para auditoria. Serializado.
    preset: str | None = None
    preset_resolved: dict[str, Any] | None = None
    #: Etapa 7 (resumo): marca que o trecho intermediário do histórico já foi
    #: resumido via LLM — a partir daí a compressão segue determinística, para
    #: limitar a 1 chamada de resumo por run. Serializado (persiste em resume).
    history_summary_done: bool = False

    devil_mode: bool = False

    # Human-in-the-loop: a run awaiting operator approval halts here.
    pending_review: dict[str, Any] | None = None
    human_decision: dict[str, Any] | None = None
    review_log: list[dict[str, Any]] = Field(default_factory=list)
    human_gate_next: str | None = None

    # Runtime-only injectable (not serialized): lets agents query data sources.
    _sources_service: Any = PrivateAttr(default=None)
    # Runtime-only injectable (not serialized): active scanning (Etapa 12).
    _scan_service: Any = PrivateAttr(default=None)
    # Runtime-only injectable (not serialized): live verification probes + the
    # operator-provided tool executor (Etapa 15 — Carro execução real).
    _verification_service: Any = PrivateAttr(default=None)
    _tool_executor: Any = PrivateAttr(default=None)
    # Runtime-only injectable (not serialized): motor de probes sob política
    # (Etapa M6) — aplica o catálogo policies/probes/*.yaml aos leads do scan.
    _probe_engine: Any = PrivateAttr(default=None)
    # Runtime-only injectable (not serialized): motor de jornadas multi-step
    # (Etapa M7-P3) — re-executa o catálogo policies/journeys/*.yaml por sessão.
    _journey_engine: Any = PrivateAttr(default=None)

    # Time de agentes disponíveis para este run (cartas ou time padrão).
    team: list[str] = Field(default_factory=list)
    # Sequência de cartas de um run de composição (vazio = modo padrão, com o
    # supervisor). É persistida junto ao estado para que a retomada (resume)
    # reconstrua o grafo linear correto em vez de recair no supervisor.
    composition: list[str] = Field(default_factory=list)
    # Agente que o Imperador escolheu para o próximo passo (reserva next_agent
    # para HITL; usado pelo router supervisor).
    delegate_to: str | None = None
    # Contador de rodadas de supervisão (proteção contra loops infinitos).
    supervisor_rounds: int = Field(default_factory=int)

    @model_validator(mode="after")
    def _trim_target_fields(self) -> GraphState:
        """Strip leading/trailing whitespace from the target name/url/notes.

        Covers every entrypoint (runs API, compositions API, CLI) so scan,
        sources and verification never see a raw name like ``" host"`` (which
        would generate an invalid URL and break host-based sources).
        """
        for key in ("name", "url", "notes", "authorization_note"):
            value = self.target.get(key)
            if isinstance(value, str):
                self.target[key] = value.strip()
        return self

    @property
    def sources_service(self) -> Any:
        return self._sources_service

    def set_sources_service(self, service: Any) -> None:
        self._sources_service = service

    @property
    def scan_service(self) -> Any:
        return self._scan_service

    def set_scan_service(self, service: Any) -> None:
        self._scan_service = service

    @property
    def verification_service(self) -> Any:
        return self._verification_service

    def set_verification_service(self, service: Any) -> None:
        self._verification_service = service

    @property
    def tool_executor(self) -> Any:
        return self._tool_executor

    def set_tool_executor(self, executor: Any) -> None:
        self._tool_executor = executor

    @property
    def probe_engine(self) -> Any:
        return self._probe_engine

    def set_probe_engine(self, engine: Any) -> None:
        self._probe_engine = engine

    @property
    def journey_engine(self) -> Any:
        return self._journey_engine

    def set_journey_engine(self, engine: Any) -> None:
        self._journey_engine = engine
