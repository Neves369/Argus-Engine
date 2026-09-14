"""Rails do Modo Diabo (Etapa M5): allowlist estrita + limites duros + auditoria.

O Argus Engine não pluga backend de execução destrutiva (decisão de produto —
ver ROADMAP Etapa 2); o caminho Diabo para no HITL e reporta ``no_backend``
honestamente em vez de fabricar sucesso. Este módulo é o ponto único que
codifica **o quê** (allowlist de tools) e **quanto** (limites de probes/taxa/
tempo) o Diabo poderia tocar, e produz o trilho de auditoria desses rails.

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
