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
sources = typer.Typer(
    help="Validar fontes de dados externas ao vivo (smoke).",
    no_args_is_help=True,
)
app.add_typer(sources, name="sources")
tools = typer.Typer(
    help="Executar ferramentas de recon passivo registradas (whois/dig) contra alvos autorizados.",
    no_args_is_help=True,
)
app.add_typer(tools, name="tools")

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
    from app.orchestration.state import GraphState
    from app.scanning.service import build_scan_service
    from app.services.run_executor import execute_run
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
            scan_service = build_scan_service()
            state.set_scan_service(scan_service)
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
                await execute_run(
                    session,
                    run,
                    target_id,
                    state,
                    archetypes,
                    build_sources_service(),
                    scan_service,
                )
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


def _session_pending() -> list[dict]:
    from app.db.models import Run
    from app.db.session import async_session_factory

    async def _run() -> list[dict]:
        async with async_session_factory() as session:
            result = await session.execute(
                select(Run).where(Run.status == "pending_review").order_by(Run.id)
            )
            rows = []
            for run in result.scalars().all():
                pending = (run.result or {}).get("pending_review") or {}
                pending_id = pending.get("id")
                kind = pending.get("kind")
                context = pending.get("context")
                rows.append(
                    {
                        "id": run.id,
                        "status": run.status,
                        "approval_id": pending_id,
                        "kind": kind,
                        "context": context,
                    }
                )
            return rows

    return asyncio.run(_run())


@compose.command("pending")
def compose_pending() -> None:
    """Listar runs aguardando decisão human-in-the-loop."""
    rows = _session_pending()
    if not rows:
        console.print("Nenhum run aguardando revisão (status pending_review).")
        return
    table = Table(title="Runs aguardando revisão")
    table.add_column("Run ID")
    table.add_column("Status")
    table.add_column("Approval ID")
    table.add_column("Kind")
    table.add_column("Contexto")
    for row in rows:
        table.add_row(
            str(row["id"]),
            row["status"],
            str(row["approval_id"]),
            row["kind"] or "-",
            row["context"] or "-",
        )
    console.print(table)


@compose.command("review")
def compose_review(
    run_id: int,
    approve: Annotated[bool, typer.Option("--approve", help="Aprovar a ação")] = False,
    reject: Annotated[bool, typer.Option("--reject", help="Rejeitar a ação")] = False,
    note: Annotated[str | None, typer.Option("--note", help="Nota do operador")] = None,
    yes: Annotated[bool, typer.Option("--yes", help="Confirma sem perguntar")] = False,
) -> None:
    """Responder a uma decisão human-in-the-loop de um run (approve/reject)."""
    if approve == reject:
        console.print("[red]Informe exatamente uma das flags --approve ou --reject.[/red]")
        raise typer.Exit(code=1)

    row = _session_get_pending(run_id)
    if row is None:
        console.print(f"[red]Run #{run_id} não encontrado ou não está em pending_review.[/red]")
        raise typer.Exit(code=1)

    console.print(f"[bold]Run #{run_id}[/bold] — {row['kind']}")
    console.print(f"  approval_id: {row['approval_id']}")
    console.print(f"  contexto: {row['context']}")
    if not yes and not typer.confirm(
        f"{( 'Aprovar' if approve else 'Rejeitar')} esta ação?", default=False
    ):
        console.print("Cancelado.")
        raise typer.Exit(code=1)

    try:
        status = _session_review(run_id, approve, note)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    console.print(f"[green]Run #{run_id}[/green] decidido — status: {status}")


def _session_get_pending(run_id: int) -> dict | None:
    from app.db.models import Run
    from app.db.session import async_session_factory

    async def _run() -> dict | None:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            if run is None or run.status != "pending_review":
                return None
            pending = (run.result or {}).get("pending_review") or {}
            return {
                "approval_id": pending.get("id"),
                "kind": pending.get("kind"),
                "context": pending.get("context"),
            }

    return asyncio.run(_run())


def _session_review(run_id: int, approved: bool, note: str | None) -> str:
    from app.core.security import is_kill_switch_active
    from app.db.models import Run
    from app.db.session import async_session_factory
    from app.scanning.service import build_scan_service
    from app.services.run_executor import resume_run

    async def _run() -> str:
        async with async_session_factory() as session:
            if is_kill_switch_active():
                raise RuntimeError("Kill switch is active")
            run = await session.get(Run, run_id)
            if run is None:
                raise ValueError(f"Run #{run_id} not found")
            pending = (run.result or {}).get("pending_review") or {}
            decision = {"id": pending.get("id"), "approved": approved, "note": note}
            await resume_run(session, run, decision, scan_service=build_scan_service())
            return run.status

    return asyncio.run(_run())


@sources.command("smoke")
def sources_smoke(
    keyword: Annotated[
        str,
        typer.Option(
            "--keyword", help="Produto+versão a correlacionar (ex.: apache http server 2.4.49)"
        ),
    ] = "apache http server 2.4.49",
) -> None:
    """Validar NVD / CISA KEV / CVE.report ao vivo (+ correlação).

    Faz requisições reais contra as APIS públicas usando o mesmo
    ``DataSourceService`` do pipeline e imprime os shapes normalizados —
    para conferir se os dados reais ainda batem com os extractors parsers
    (NVD pode adicionar CVSS v4, mudar campos, etc.).
    """
    from app.scanning.service import ScanReport
    from app.scanning.spec import TargetPage
    from app.services.cve_correlate import correlate_scan_report
    from app.sources.service import build_sources_service

    async def _probe() -> None:
        service = build_sources_service()

        kev = await service.query("kev", {})
        console.print(f"[bold]kev[/bold] status={kev['status']}")
        if kev["status"] in ("ok", "cache"):
            entries = (kev.get("data") or {}).get("vulnerabilities") or []
            console.print(f"  catalogo={kev['data'].get('catalogVersion')} entradas={len(entries)}")

        corpus = {
            "target": "example.com",
            "pages": [
                TargetPage(
                    url="http://example.com/",
                    status_code=200,
                    headers={"server": "Apache/2.4.49 (Ubuntu)"},
                    body="<html><body>x</body></html>",
                )
            ],
        }
        report = ScanReport(**corpus)
        correlated = await correlate_scan_report(report, service)
        console.print(f"[bold]correlacao[/bold] findings={len(correlated)}")
        for finding in correlated:
            console.print(f"  title={finding['title']}")
            console.print(f"  severity={finding['severity']} cvss={finding['cvss_score']}")
            console.print(f"  cves={finding['cves']}")
            console.print(f"  known_exploits={len(finding['known_exploits'])}")
            console.print(f"  references={len(finding['references'])}")
            console.print(f"  status={finding['status']} review={finding['requires_human_review']}")

        # NVD raw shape after the correlation — it owns the first-burst slot so
        # this follow-up read may legitimately be rate-limited (deterministic
        # degradation, not an error). The correlation result above is the
        # meaningful signal.
        nvd = await service.query(
            "nvd",
            {
                "keywordSearch": keyword,
                "resultsPerPage": "5",
            },
        )
        console.print(f"[bold]nvd[/bold] status={nvd['status']}")
        if nvd["status"] in ("ok", "cache"):
            vulns = (nvd.get("data") or {}).get("vulnerabilities") or []
            console.print(f"  totalResults={nvd['data'].get('totalResults')} vulns={len(vulns)}")
            if vulns:
                cve = vulns[0].get("cve") or {}
                cvss_keys = list((cve.get("metrics") or {}).keys()) or []
                console.print(f"  primeiro: {cve.get('id')} cvss-keys={cvss_keys}")

    try:
        asyncio.run(_probe())
    except Exception as exc:  # noqa: BLE001
        console.print(f"[red]Smoke falhou:[/red] {exc}")
        raise typer.Exit(code=1) from exc


@tools.command("run")
def tools_run(
    tool: Annotated[str, typer.Argument(help="Nome da tool registrada (ex.: whois, dig)")],
    target: Annotated[str, typer.Argument(help="Alvo autorizado (scope)")],
) -> None:
    """Executar uma tool de recon passivo registrada contra um alvo autorizado.

    Usa o mesmo ``ToolRegistry``/``ToolExecutor`` da API; valida o alvo contra
    ``ALLOWED_SCOPES`` antes de rodar e degrada de forma determinística quando
    o binário não está instalado ou a rede bloqueia a chamada (nunca um 500).
    """
    from app.core.config import get_settings
    from app.core.security import ScopeValidationError, validate_scope
    from app.tools import ToolExecutionError, ToolExecutor, ToolRegistry
    from app.tools.spec import ToolKind

    registry = ToolRegistry()
    registry.load(get_settings().tools_manifest)
    try:
        spec = registry.get_tool(tool)
    except KeyError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc
    if spec.kind != ToolKind.CLI or spec.destructive:
        console.print("[red]Tool não é um comando CLI passivo seguro.[/red]")
        raise typer.Exit(code=1)
    try:
        validate_scope(target)
    except ScopeValidationError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    try:
        result = asyncio.run(ToolExecutor(registry).execute(tool, {"target": target}))
    except ToolExecutionError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(f"[bold]{tool} {target}[/bold] returncode={result['returncode']}")
    if result["returncode"] == 0 and result["stdout"]:
        console.print(result["stdout"])
    else:
        console.print(f"[yellow]sem saída / egress bloqueado:[/yellow] {result['stderr'] or '-'}")


if __name__ == "__main__":
    app()
