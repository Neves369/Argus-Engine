from __future__ import annotations

import hashlib


def finding_fingerprint(title: str, category: str | None, affected: str | None) -> str:
    """Assinatura estável de um finding lógico (M9-P0).

    Identidade derivada de título + categoria + afetado normalizados — sem
    id/run/severity/confidence, para que o MESMO achado observado em runs
    distintos produza o mesmo hash (base do diff e do dedup global). O sha256
    é truncado para 32 caracteres hex (colisão improvável no escopo de um alvo).
    """
    norm = "\x00".join(
        [
            (title or "").strip().lower(),
            (category or "").strip().lower(),
            (affected or "").strip().lower(),
        ]
    )
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]
