from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

from app.journeys.schemas import Journey

JOURNEYS_PATH = Path(__file__).resolve().parents[2] / "policies" / "journeys"
CATALOG_VERSION = "1.0.0"


@lru_cache
def load_catalog() -> dict[str, Journey]:
    """Registry de jornadas versionadas, chaveado por ``id``.

    Fail-closed igual ao catálogo de probes (M6): jornada inválida ou ``id``
    duplicado aborta o load — um catálogo parcial nunca governa um run.
    """
    journeys: dict[str, Journey] = {}
    if not JOURNEYS_PATH.is_dir():
        return journeys
    for path in sorted(JOURNEYS_PATH.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        journey = Journey.model_validate(data)
        if journey.id in journeys:
            raise ValueError(f"Duplicate journey id: {journey.id}")
        journeys[journey.id] = journey
    return journeys


def journey_digest(journey: Journey) -> str:
    """sha256 estável do modelo canônico da jornada (para auditoria)."""
    canonical = yaml.safe_dump(journey.model_dump(), sort_keys=True, allow_unicode=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_journey_ids(limit: str = "p0") -> list[str]:
    """Ids habilitados pelo allowlist de prioridade do operador."""
    _PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2, "p3": 3}
    key = (limit or "p0").strip().lower()
    allow = _PRIORITY_ORDER.get(key, 0)
    catalog = load_catalog()
    return sorted(
        j.id
        for j in catalog.values()
        if _PRIORITY_ORDER.get(j.priority.lower(), 99) <= allow and j.default_enabled
    )


def journey_manifest() -> dict:
    """Versão + digest por jornada, para registrar o que governou o run."""
    catalog = load_catalog()
    return {
        "version": CATALOG_VERSION,
        "journeys": {
            jid: {
                "version": j.version,
                "priority": j.priority,
                "default_enabled": j.default_enabled,
                "sha256": journey_digest(j),
            }
            for jid, j in sorted(catalog.items())
        },
    }