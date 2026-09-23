"""Presets Tarot (Etapa M10-P3): composições prontas de cartas.

Um preset é uma composição de arquétipos versionada e pronta para uso — o
operador escolhe por nome (``recon``/``app-map``/``deep-web``/``api``) em vez de
montar a sequência de cartas na mão. Cada preset pareia uma sequência de cartas
(via ``validate_sequence``: sem repetição, sem ``emperor``, fechada por
``justice``) com um pacote de política (M10-P0) que define depth/probes/jornadas.

Fail-closed: id desconhecido → ``KeyError``; sequência de cartas inválida ou
referência a pacote inexistente → ``ValueError``. Os presets vivem em
``policies/presets/*.yaml``.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from app.orchestration.compose import validate_sequence
from app.policies.packages import load_packages

PRESETS_PATH = Path(__file__).resolve().parents[2] / "policies" / "presets"


class TarotPreset(BaseModel):
    """Um preset de composição, como declarado no YAML."""

    id: str
    version: str
    name: str
    description: str = ""
    archetypes: list[str] = Field(min_length=1)
    policy_package: str | None = None


class PresetRead(BaseModel):
    """Preset resolvido, pronto para governar (e auditar) a composição."""

    id: str
    version: str
    name: str
    description: str
    archetypes: list[str]
    policy_package: str | None
    sha256: str


@lru_cache
def load_presets() -> dict[str, TarotPreset]:
    """Registry de presets, chaveado por ``id`` (fail-closed, como os demais)."""
    presets: dict[str, TarotPreset] = {}
    if not PRESETS_PATH.is_dir():
        return presets
    for path in sorted(PRESETS_PATH.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        preset = TarotPreset.model_validate(data)
        if preset.id in presets:
            raise ValueError(f"Duplicate preset id: {preset.id}")
        presets[preset.id] = preset
    return presets


def preset_digest(preset: TarotPreset) -> str:
    """sha256 estável do modelo canônico do preset (para auditoria)."""
    canonical = yaml.safe_dump(preset.model_dump(), sort_keys=True, allow_unicode=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_preset(preset: TarotPreset) -> None:
    validate_sequence(preset.archetypes)
    if preset.policy_package and preset.policy_package not in load_packages():
        raise ValueError(
            f"Preset '{preset.id}': pacote de política desconhecido: {preset.policy_package}"
        )


def resolve_preset(preset_id: str) -> PresetRead:
    """Resolve um preset; ``KeyError`` se o id não existir, ``ValueError`` se inválido."""
    preset = load_presets().get(preset_id)
    if preset is None:
        raise KeyError(preset_id)
    _validate_preset(preset)
    return PresetRead(
        id=preset.id,
        version=preset.version,
        name=preset.name,
        description=preset.description,
        archetypes=list(preset.archetypes),
        policy_package=preset.policy_package,
        sha256=preset_digest(preset),
    )


def list_presets() -> list[PresetRead]:
    """Todos os presets resolvidos, em ordem de id (para a UI/CLI)."""
    return [resolve_preset(pid) for pid in sorted(load_presets())]


def run_preset(
    preset_id: str | None,
    *,
    archetypes: list[str] | None,
    policy_package: str | None,
) -> dict[str, Any]:
    """Política de composição efetiva: preset (autoritativo) ou campos explícitos.

    Quando ``preset_id`` é definido, a sequência de cartas vem do preset e o
    ``policy_package`` explícito (se houver) vence o do preset; caso contrário
    usa-se o pacote do próprio preset. Sempre devolve o id do preset e o
    snapshot resolvido (``preset_resolved``) para auditoria.
    """
    if preset_id:
        resolved = resolve_preset(preset_id)
        return {
            "preset": resolved.id,
            "archetypes": resolved.archetypes,
            "policy_package": policy_package or resolved.policy_package,
            "preset_resolved": {
                "id": resolved.id,
                "version": resolved.version,
                "name": resolved.name,
                "archetypes": resolved.archetypes,
                "policy_package": resolved.policy_package,
                "sha256": resolved.sha256,
            },
        }
    return {
        "preset": None,
        "archetypes": archetypes,
        "policy_package": policy_package,
        "preset_resolved": None,
    }
