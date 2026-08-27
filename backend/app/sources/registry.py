from __future__ import annotations

import json
from pathlib import Path

from app.sources.spec import DataSourceSpec


class DataSourceRegistry:
    """Loads data source specs from a JSON manifest and exposes lookup."""

    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self._sources: dict[str, DataSourceSpec] = {}
        self._path = Path(manifest_path) if manifest_path else None
        if manifest_path is not None:
            self.load(manifest_path)

    def load(self, path: str | Path) -> None:
        manifest = Path(path)
        if not manifest.exists():
            return
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for raw in data:
            spec = DataSourceSpec.model_validate(raw)
            self._sources[spec.name] = spec

    def register(self, spec: DataSourceSpec) -> None:
        self._sources[spec.name] = spec

    def get_source(self, name: str) -> DataSourceSpec:
        try:
            return self._sources[name]
        except KeyError:
            raise KeyError(f"Unknown source: {name}") from None

    def available_sources(self) -> list[str]:
        return list(self._sources)

    def has_source(self, name: str) -> bool:
        return name in self._sources
