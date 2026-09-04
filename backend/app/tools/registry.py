from __future__ import annotations

import json
from pathlib import Path

from app.tools.spec import ToolSpec


class ToolRegistry:
    """Loads tool specs from a JSON manifest and exposes lookup/authorization."""

    def __init__(self, manifest_path: str | Path | None = None) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._path = Path(manifest_path) if manifest_path else None

    def load(self, path: str | Path) -> None:
        manifest = Path(path)
        if not manifest.exists():
            return
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for raw in data:
            spec = ToolSpec.model_validate(raw)
            self._tools[spec.name] = spec

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get_tool(self, name: str) -> ToolSpec:
        try:
            return self._tools[name]
        except KeyError:
            raise KeyError(f"Unknown tool: {name}") from None

    def available_tools(self) -> list[str]:
        return list(self._tools)

    @staticmethod
    def authorize(tool: ToolSpec, allowed_tools: tuple[str, ...]) -> bool:
        if "*" in allowed_tools:
            return True
        return tool.name in allowed_tools
