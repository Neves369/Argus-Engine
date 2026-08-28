from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy import select

app = typer.Typer(
    name="argus",
    help="Argus Engine — composição e execução de grafos de arquétipos (CLI).",
    no_args_is_help=True,
)
compose = typer.Typer(
    help="Gerenciar composições de grafo (criar, listar, detalhar, executar, exportar).",
    no_args_is_help=True,
)
app.add_typer(compose, name="compose")

console = Console()


def _utcnow() -> datetime:
    return datetime.now(UTC)


@app.callback()
def _main() -> None:
    """Ensure the database is migrated before any command runs."""
    from app.db.migrate import upgrade_sync

    upgrade_sync()


@app.command("validate")
def validate_cmd(
    archetypes: Annotated[list[str], typer.Argument(help="Sequência de arquétipos")],
) -> None:
    """Validate an archetype sequence without persisting anything."""
    from app.orchestration.compose import validate_sequence

    try:
        validate_sequence(archetypes)
        console.print(f"[green]OK[/green] — sequência válida: {', '.join(archetypes)}")
    except ValueError as exc:
        console.print(f"[red]Inválido[/red]: {exc}")
        raise typer.Exit(code=1) from exc


def _session_create(
    name: str, archetypes: list[str], target: str | None, url: str | None, devil: bool
) -> int:
    from app.db.models import Session
    from app.db.session import async_session_factory
    from app.orchestration.compose import validate_sequence

    validate_sequence(archetypes)
    config: dict = {"archetypes": archetypes, "target": None, "devil_mode": devil}
    if target:
        config["target"] = {"name": target, "url": url, "notes": None}

    async def _run() -> int:
        async with async_session_factory() as session:
            record = Session(name=name, status="open", config=config)
            session.add(record)
            await session.commit()
            await session.refresh(record)
            return record.id

    return asyncio.run(_run())


@compose.command("create")
def compose_create(
    name: str,
    archetypes: Annotated[list[str], typer.Argument(help="Sequência; última deve ser justice")],
    target: Annotated[str | None, typer.Option("--target", help="Alvo autorizado (scope)")] = None,
    url: Annotated[str | None, typer.Option("--url")] = None,
    devil: Annotated[bool, typer.Option("--devil", help="Modo Diabo")] = False,
) -> None:
    """Criar e salvar uma composição de grafo."""
    try:
        session_id = _session_create(name, archetypes, target, url, devil)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Composição criada[/green] #id {session_id}: {name}")


def _session_list() -> list[dict]:
    from app.db.models import Session
    from app.db.session import async_session_factory

    async def _run() -> list[dict]:
        async with async_session_factory() as session:
            result = await session.execute(select(Session).order_by(Session.id))
            rows = [
                {
                    "id": r.id,
                    "name": r.name,
                    "status": r.status,
                    "archetypes": (r.config or {}).get("archetypes", []),
                }
                for r in result.scalars().all()
            ]
            return rows

    return asyncio.run(_run())


@compose.command("list")
def compose_list() -> None:
    """Listar composições salvas."""
    rows = _session_list()
    if not rows:
        console.print("Nenhuma composição salva.")
        return
    table = Table(title="Composições")
    table.add_column("ID")
    table.add_column("Nome")
    table.add_column("Status")
    table.add_column("Arquétipos")
    for row in rows:
        table.add_row(str(row["id"]), row["name"], row["status"], " → ".join(row["archetypes"]))
    console.print(table)


@compose.command("get")
def compose_get(composition_id: int) -> None:
    """Mostrar detalhes de uma composição."""
    from app.db.models import Session
    from app.db.session import async_session_factory

    async def _run() -> dict | None:
        async with async_session_factory() as session:
            row = await session.get(Session, composition_id)
            if row is None:
                return None
            return {
                "id": row.id,
                "name": row.name,
                "status": row.status,
                "target_id": row.target_id,
                "config": row.config,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }

    data = asyncio.run(_run())
    if data is None:
        console.print(f"[red]Composição #{composition_id} não encontrada.[/red]")
        raise typer.Exit(code=1)
    for key, value in data.items():
        console.print(f"{key}: {value}")


def _session_execute(composition_id: int) -> tuple[int, str]:
    from app.core.security import is_kill_switch_active, validate_scope
    from app.db.models import Run, Session, Target
    from app.db.session import async_session_factory
    from app.orchestration.compose import validate_sequence
    from app.orchestration.director import Director
    from app.orchestration.state import GraphState
    from app.services.persistence import persist_run_result
    from app.sources.service import build_sources_service

    async def _run() -> tuple[int, str]:
        async with async_session_factory() as session:
            if is_kill_switch_active():
                raise RuntimeError("Kill switch is active")
            record = await session.get(Session, composition_id)
            if record is None:
                raise ValueError(f"Composition #{composition_id} not found")

            config = record.config or {}
            archetypes = config.get("archetypes", [])
            validate_sequence(archetypes)

            target = config.get("target") or {}
            target_name = str(target.get("name", ""))
            if target_name:
                validate_scope(target_name)

            target_id = record.target_id
            if target_name and target_id is None:
                new_target = Target(
                    name=target_name,
                    url=target.get("url"),
                    notes=target.get("notes"),
                )
                session.add(new_target)
                await session.flush()
                target_id = new_target.id
                record.target_id = target_id

            state = GraphState(target=target, devil_mode=bool(config.get("devil_mode", False)))
            state.set_sources_service(build_sources_service())
            run = Run(
                target_id=target_id,
                session_id=record.id,
                status="running",
                started_at=_utcnow(),
            )
            session.add(run)
            await session.flush()
            run_id = run.id

            try:
                final_state = await Director(archetypes).run(state)
                run.status = "completed"
                run.result = final_state.model_dump()
                await persist_run_result(session, run_id, target_id, final_state)
            except Exception as exc:  # noqa: BLE001
                run.status = "failed"
                run.error = str(exc)
            finally:
                run.finished_at = _utcnow()
                record.status = "done"

            await session.commit()
            return run_id, run.status

    return asyncio.run(_run())


@compose.command("execute")
def compose_execute(composition_id: int) -> None:
    """Executar uma composição salva (resolve alvo + roda o grafo)."""
    try:
        run_id, status = _session_execute(composition_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Run #{run_id}[/green] status: {status}")


@compose.command("export")
def compose_export(
    composition_id: int,
    fmt: Annotated[str, typer.Option("--fmt", help="json|yaml")] = "json",
    out: Annotated[
        str | None, typer.Option("--out", help="Caminho do arquivo; default stdout")
    ] = None,
) -> None:
    """Exportar uma composição (para JSON/YAML)."""
    from app.db.models import Run, Session
    from app.db.session import async_session_factory
    from app.services.export import serialize

    async def _run() -> str:
        async with async_session_factory() as session:
            row = await session.get(Session, composition_id)
            if row is None:
                raise ValueError(f"Composition #{composition_id} not found")
            runs_result = await session.execute(select(Run).where(Run.session_id == row.id))
            runs = list(runs_result.scalars().all())
        from app.services.export import composition_to_dict, run_to_dict

        data = {
            "composition": composition_to_dict(row),
            "runs": [run_to_dict(r) for r in runs],
        }
        return serialize(data, fmt)

    try:
        payload = asyncio.run(_run())
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if out:
        with open(out, "w", encoding="utf-8") as handle:
            handle.write(payload)
        console.print(f"[green]Exportado[/green] para {out} ({fmt})")
    else:
        console.print(payload)


if __name__ == "__main__":
    app()
