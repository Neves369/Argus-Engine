"""Pacotes de política (Etapa M10-P0).

Um pacote de política é a "política do run" expressa como um único identificador
que o operador escolhe — sem editar YAML na mão. Cada pacote versiona
``depth``, as classes de probe M6 liberadas (allowlist), as jornadas M7-P3 e o
``devil_mode``. A resolução é fail-closed: id desconhecido → ``KeyError``;
referência a classe/jornada inexistente no catálogo → ``ValueError``.

Os pacotes vivem em ``policies/packages/*.yaml`` e referenciam apenas classes
que já existem nos catálogos versionados de probes e jornadas — o pacote nunca
inventa uma classe, apenas compõe o que já está aprovado.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from app.journeys.catalog import load_catalog as load_journey_catalog
from app.probing.catalog import load_catalog as load_probe_catalog

PACKAGES_PATH = Path(__file__).resolve().parents[2] / "policies" / "packages"


class PolicyPackage(BaseModel):
    """Um pacote de política versionado, como declarado no YAML."""

    id: str
    version: str
    name: str
    description: str = ""
    depth: Literal["quick", "deep"] = "quick"
    #: Allowlist de classes de probe (ids do catálogo M6). Vazio = nenhuma.
    probe_classes: list[str] = Field(default_factory=list)
    #: Jornadas multi-step liberadas (ids do catálogo M7-P3). Vazio = nenhuma.
    journey_classes: list[str] = Field(default_factory=list)
    devil_mode: bool = False


class PolicyPackageRead(BaseModel):
    """Pacote resolvido, pronto para governar (e auditar) um run."""

    id: str
    version: str
    name: str
    description: str
    depth: str
    probe_classes: list[str]
    journey_classes: list[str]
    devil_mode: bool
    sha256: str


@lru_cache
def load_packages() -> dict[str, PolicyPackage]:
    """Registry de pacotes de política, chaveado por ``id``.

    Fail-closed igual aos catálogos de probes/jornadas: pacote inválido ou id
    duplicado aborta o load — um registry parcial nunca governa um run.
    """
    packages: dict[str, PolicyPackage] = {}
    if not PACKAGES_PATH.is_dir():
        return packages
    for path in sorted(PACKAGES_PATH.glob("*.yaml")):
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        package = PolicyPackage.model_validate(data)
        if package.id in packages:
            raise ValueError(f"Duplicate policy package id: {package.id}")
        packages[package.id] = package
    return packages


def package_digest(package: PolicyPackage) -> str:
    """sha256 estável do modelo canônico do pacote (para auditoria/reprodução)."""
    canonical = yaml.safe_dump(package.model_dump(), sort_keys=True, allow_unicode=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_references(package: PolicyPackage) -> None:
    probes = load_probe_catalog()
    journeys = load_journey_catalog()
    for cid in package.probe_classes:
        if cid not in probes:
            raise ValueError(f"Policy package '{package.id}': classe de probe desconhecida: {cid}")
    for jid in package.journey_classes:
        if jid not in journeys:
            raise ValueError(f"Policy package '{package.id}': jornada desconhecida: {jid}")


def resolve_package(package_id: str) -> PolicyPackageRead:
    """Resolve um pacote contra os catálogos; ``KeyError`` se o id não existir."""
    package = load_packages().get(package_id)
    if package is None:
        raise KeyError(package_id)
    _validate_references(package)
    return PolicyPackageRead(
        id=package.id,
        version=package.version,
        name=package.name,
        description=package.description,
        depth=package.depth,
        probe_classes=list(package.probe_classes),
        journey_classes=list(package.journey_classes),
        devil_mode=package.devil_mode,
        sha256=package_digest(package),
    )


def list_packages() -> list[PolicyPackageRead]:
    """Todos os pacotes resolvidos, em ordem de id (para a UI/CLI)."""
    return [resolve_package(pid) for pid in sorted(load_packages())]


def apply_package(package_id: str) -> dict[str, Any]:
    """Resolve um pacote nas efetivas "políticas de run".

    Retorna um dict pronto para alimentar ``GraphState`` (``depth``,
    ``probe_classes``, ``journey_classes``, ``devil_mode``) mais o id do pacote
    e um snapshot resolvido (``policy_resolved``) para auditoria/reprodução.
    Levanta ``KeyError`` para id desconhecido.
    """
    resolved = resolve_package(package_id)
    return {
        "policy_package": resolved.id,
        "depth": resolved.depth,
        "probe_classes": resolved.probe_classes or None,
        "journey_classes": resolved.journey_classes or None,
        "devil_mode": resolved.devil_mode,
        "policy_resolved": {
            "id": resolved.id,
            "version": resolved.version,
            "name": resolved.name,
            "depth": resolved.depth,
            "probe_classes": resolved.probe_classes,
            "journey_classes": resolved.journey_classes,
            "devil_mode": resolved.devil_mode,
            "sha256": resolved.sha256,
        },
    }


def run_policy(
    package_id: str | None,
    *,
    depth: str,
    probe_classes: list[str] | None,
    journey_classes: list[str] | None,
    devil_mode: bool,
) -> dict[str, Any]:
    """Política efetiva do run: pacote (autoritativo) ou campos explícitos.

    Quando ``package_id`` é definido, o pacote governa ``depth``/
    ``probe_classes``/``journey_classes``/``devil_mode`` e os campos explícitos
    são ignorados (o operador que quer fine-tuning não usa pacote). Caso
    contrário, os campos explícitos passam intactos. Sempre devolve o id do
    pacote e o snapshot resolvido (``policy_resolved``) para auditoria.
    """
    if package_id:
        return apply_package(package_id)
    return {
        "policy_package": None,
        "depth": depth,
        "probe_classes": probe_classes,
        "journey_classes": journey_classes,
        "devil_mode": devil_mode,
        "policy_resolved": None,
    }
