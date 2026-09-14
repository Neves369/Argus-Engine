from __future__ import annotations

from app.db.models import Finding

#: Ruído de lab/CDN (Etapa M4) — leads puramente informativos que não sinalizam
#: risco real e inflariam o relatório sem valor. São suprimidos no pipeline de
#: validação como falsos positivos conhecidos (mesclados com `FP_BLACKLIST` e
#: com as regras aprendidas em `findings.py`).
BUILTIN_FP_NOISE: tuple[str, ...] = (
    "servido por proxy ou data center",
    "stack de tecnologia identificada no alvo",
)


class FalsePositiveBlacklist:
    """Matches findings against known false-positive signatures (local knowledge)."""

    def __init__(self, patterns: list[str] | None = None) -> None:
        self._patterns = [pattern.lower() for pattern in (patterns or []) if pattern]

    def matches(self, finding: Finding) -> bool:
        haystack = " ".join(
            part for part in (finding.title, finding.description or "") if part
        ).lower()
        return any(pattern in haystack for pattern in self._patterns)
