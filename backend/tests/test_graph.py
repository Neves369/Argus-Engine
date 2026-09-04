from __future__ import annotations

import asyncio

from app.orchestration.director import Director
from app.orchestration.state import GraphState


def test_graph_runs_to_completion():
    async def _run() -> GraphState:
        director = Director()
        state = GraphState(target={"name": "example.com"})
        return await director.run(state)

    final = asyncio.run(_run())

    assert final.stop_reason == "completed"
    assert len(final.history) >= 3
    # No sources_service configured -> no real signal -> no findings
    # fabricated (see app.services.source_findings for the real derivation).
    assert final.findings == []
    assert final.tokens_used > 0
    assert final.confidence >= 0.6
