from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Run
from app.orchestration.director import Director
from app.orchestration.hitl import is_awaiting_review
from app.orchestration.state import GraphState
from app.services.persistence import persist_run_result
from app.services.run_control import clear_cancel, is_cancel_requested
from app.sources.service import build_sources_service

#: Estados de um run que param no meio do caminho mas guardaram estado
#: persistido — retomáveis de onde pararam (Retomada geral — Etapa 14).
RESUMABLE_STATUSES: tuple[str, ...] = ("cancelled", "failed")


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def execute_run(
    db: AsyncSession,
    run: Run,
    target_id: int | None,
    state: GraphState,
    archetypes: list[str] | None,
    sources_service: Any,
    scan_service: Any | None = None,
) -> GraphState:
    """Execute a graph run, finalizing it or halting for a human decision."""
    director = Director(
        archetypes,
        sources_service=sources_service,
        scan_service=scan_service,
    )
    final = await director.run(state)
    if is_awaiting_review(final):
        run.status = "pending_review"
        run.result = final.model_dump()
    else:
        run.status = "completed"
        run.result = final.model_dump()
        await persist_run_result(db, run.id, target_id, final)
    return final


async def resume_run(
    db: AsyncSession,
    run: Run,
    decision: dict[str, Any],
    *,
    sources_service: Any | None = None,
    scan_service: Any | None = None,
) -> GraphState:
    """Apply a human decision to a pending review and resume the run.

    Raises ``ValueError`` with a user-facing message when the run is not
    awaiting the supplied approval.
    """
    if run.status != "pending_review" or not run.result:
        raise ValueError("Run is not awaiting review")

    saved = run.result
    pending = saved.get("pending_review")
    if not pending:
        raise ValueError("Run has no pending review")
    if str(pending.get("id")) != str(decision.get("id")):
        raise ValueError("approval_id mismatch")

    state = GraphState.model_validate(saved)
    state.set_sources_service(sources_service or build_sources_service())
    if scan_service is not None:
        state.set_scan_service(scan_service)
    state.human_decision = decision

    composition = state.composition or None
    director = Director(
        archetypes=composition,
        sources_service=sources_service or build_sources_service(),
        scan_service=scan_service,
    )
    entry = state.next_agent or (composition[0] if composition else "emperor")
    final = await director.run_from(state, entry)
    if is_awaiting_review(final):
        run.status = "pending_review"
    else:
        run.status = "completed"
        await persist_run_result(db, run.id, run.target_id, final)
    run.result = final.model_dump()
    run.finished_at = _utcnow()
    await db.commit()
    return final


def state_from_run(
    run: Run,
    *,
    sources_service: Any | None = None,
    scan_service: Any | None = None,
) -> GraphState:
    """Reconstruir o estado persistido de um run para retomá-lo.

    Levanta ``ValueError`` quando o run não guardou estado resumível.
    """
    if not run.result:
        raise ValueError("Run não possui estado persistido para retomar")
    state = GraphState.model_validate(run.result)
    state.set_sources_service(sources_service or build_sources_service())
    if scan_service is not None:
        state.set_scan_service(scan_service)
    return state


async def stream_run_events(
    db: AsyncSession,
    run: Run,
    state: GraphState,
    director: Director,
    *,
    entry: str | None = None,
) -> AsyncGenerator[str, None]:
    """Gera os frames SSE de um run executando nó a nó e finaliza o ``Run``.

    Comum a um run novo (``/runs/stream``) e a uma retomada
    (``/runs/{id}/resume``): emite ``start``/``node``/``error``/``done``,
    respeita cancelamento, e persiste o estado (resultado ou parcial, para
    que uma nova retomada seja possível) no fim.
    """
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    event_id = 0

    def make(event: str, data: dict[str, Any]) -> str:
        nonlocal event_id
        event_id += 1
        return (
            f"id: {event_id}\nevent: {event}\n"
            f"data: {json.dumps(data, default=str)}\n\n"
        )

    async def producer() -> None:
        await queue.put("retry: 3000\n\n")
        await queue.put(make("start", {"run_id": run.id}))
        final = state.model_dump()
        try:
            async for chunk in director.stream(state, entry=entry):
                if is_cancel_requested(run.id):
                    run.status = "cancelled"
                    run.result = final
                    break
                for node, update in chunk.items():
                    final.update(update)
                    await queue.put(make("node", {"node": node, "update": update}))
            else:
                final_state = GraphState.model_validate(final)
                if is_awaiting_review(final_state):
                    run.status = "pending_review"
                else:
                    run.status = "completed"
                    await persist_run_result(db, run.id, run.target_id, final_state)
                run.result = final
        except Exception as exc:  # noqa: BLE001
            run.status = "failed"
            run.error = str(exc)
            # Persiste o estado parcial: permite retomar de onde parou depois.
            run.result = final
            await queue.put(make("error", {"message": str(exc)}))
        finally:
            clear_cancel(run.id)
            run.finished_at = _utcnow()

        await db.commit()
        await queue.put(make("done", {"run_id": run.id, "status": run.status}))
        await queue.put(None)

    async def heartbeat() -> None:
        try:
            while True:
                await asyncio.sleep(15)
                await queue.put(": ping\n\n")
        except asyncio.CancelledError:
            return

    async def consumer() -> AsyncGenerator[str, None]:
        producer_task = asyncio.create_task(producer())
        heartbeat_task = asyncio.create_task(heartbeat())
        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
        finally:
            producer_task.cancel()
            heartbeat_task.cancel()

    async for chunk in consumer():
        yield chunk
