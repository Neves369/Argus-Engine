"""Rails do Modo Diabo (Etapa M5): allowlist estrita + limites duros + auditoria.

Este módulo é o ponto único que codifica **o quê** (allowlist de tools) e
**quanto** (limites de probes/taxa/tempo) o Diabo pode tocar, e produz o trilho
de auditoria desses rails. O backend de execução controlada (Carro em devil
mode) aplica estes rails ao invocar, após aprovação HITL, as tools da allowlist
via ``ToolExecutor`` — ver ``ChariotAgent._controlled_execution``.

Sem ``devil_mode`` nenhum código do Diabo é alcançado — a fronteira é
``is_devil_mode_enabled`` em ``app/core/security.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import get_settings


@dataclass
class DevilGuard:
    """Controla o escopo de atuação do Modo Diabo (nunca solto)."""

    allowed_tools: frozenset[str] = field(default_factory=frozenset)
    max_probes: int = 0
    max_rate: float = 0.0
    max_duration_seconds: int = 0

    def allows(self, tool_name: str) -> bool:
        """True quando a tool está na allowlist estrita do Diabo."""
        return tool_name in self.allowed_tools

    def resolve_tools(self, tool_names: list[str]) -> list[str]:
        """Filtra nomes de tools para as permitidas ao Diabo (ordem preservada)."""
        return [name for name in tool_names if self.allows(name)]

    def within_limits(self, probes_done: int, elapsed_seconds: float) -> bool:
        """True enquanto o stress controlado estiver dentro dos limites duros.

        ``probes_done`` é o total de probes já executados pelo Diabo no run e
        ``elapsed_seconds`` o tempo decorrido desde o início do passo.
        """
        if self.max_probes > 0 and probes_done >= self.max_probes:
            return False
        if self.max_duration_seconds > 0 and elapsed_seconds >= self.max_duration_seconds:
            return False
        return True

    @property
    def min_interval_seconds(self) -> float:
        """Intervalo mínimo entre probes imposto pelo teto de taxa.

        ``max_rate`` é requisições/minuto; ``0`` (ou negativo) desliga o throttle.
        """
        if self.max_rate <= 0:
            return 0.0
        return 60.0 / self.max_rate

    def throttle_delay_seconds(self, elapsed_since_last: float) -> float:
        """Quanto (segundos) dormir antes da próxima probe para respeitar a taxa.

        Nunca negativo; ``0.0`` quando a última probe já está longe o bastante
        ou quando o teto de taxa está desligado.
        """
        interval = self.min_interval_seconds
        if interval <= 0:
            return 0.0
        return max(0.0, interval - elapsed_since_last)

    def audit(self) -> dict[str, Any]:
        """Rails serializáveis para a trilha de auditoria (proposal + entry)."""
        return {
            "allowed_tools": sorted(self.allowed_tools),
            "max_probes": self.max_probes,
            "max_rate_per_minute": self.max_rate,
            "max_duration_seconds": self.max_duration_seconds,
        }


def build_devil_guard() -> DevilGuard:
    """Instancia o guard a partir das settings (``DEVIL_*``)."""
    settings = get_settings()
    return DevilGuard(
        allowed_tools=frozenset(settings.devil_allowed_tools),
        max_probes=int(settings.devil_max_probes),
        max_rate=float(settings.devil_max_rate),
        max_duration_seconds=int(settings.devil_max_duration_seconds),
    )
