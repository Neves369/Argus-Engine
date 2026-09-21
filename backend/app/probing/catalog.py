from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

import yaml

from app.probing.schemas import ProbePolicy

PROBES_PATH = Path(__file__).resolve().parents[2] / "policies" / "probes"
CATALOG_VERSION = "1.0.0"

_PRIORITY_ORDER = {"p0": 0, "p1": 1, "p2": 2}


@lru_cache
def load_catalog() -> dict[str, ProbePolicy]:
    """Registry de políticas versionadas, chaveado por ``id``.

    Falha fechado: qualquer política inválida ou id duplicado aborta o load —
    nunca um catálogo parcial governa um run. O sha256 por arquivo fica
    disponível via ``catalog_digest`` para a trilha de auditoria.
    """
    policies: dict[str, ProbePolicy] = {}
    if not PROBES_PATH.is_dir():
        return policies
    for path in sorted(PROBES_PATH.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        policy = ProbePolicy.model_validate(data)
        if policy.id in policies:
            raise ValueError(f"Duplicate probe policy id: {policy.id}")
        policies[policy.id] = policy
    return policies


def catalog_digest(policy: ProbePolicy) -> str:
    """sha256 estável do modelo canônico da política (para auditoria)."""
    canonical = yaml.safe_dump(policy.model_dump(), sort_keys=True, allow_unicode=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def default_probe_classes(limit: str = "p0") -> list[str]:
    """Classes liberadas pelo allowlist de prioridade do operador.

    ``p0`` (default seguro) → só políticas P0 com ``default_enabled``;
    ``p1`` → P0+P1; ``p2``/``all`` → P0+P1+P2. P3 (authn) fica em M7.
    """
    key = (limit or "p0").strip().lower()
    if key in ("all", "p2"):
        allow = 2
    elif key == "p1":
        allow = 1
    else:
        allow = 0
    catalog = load_catalog()
    return sorted(
        p.id
        for p in catalog.values()
        if _PRIORITY_ORDER.get(p.priority.lower(), 99) <= allow and p.default_enabled
    )


def catalog_manifest() -> dict:
    """Versão + digest por política, para registrar que catálogo governou o run."""
    catalog = load_catalog()
    return {
        "version": CATALOG_VERSION,
        "policies": {
            pid: {
                "version": p.version,
                "priority": p.priority,
                "class_label": p.class_label,
                "default_enabled": p.default_enabled,
                "sha256": catalog_digest(p),
            }
            for pid, p in sorted(catalog.items())
        },
    }