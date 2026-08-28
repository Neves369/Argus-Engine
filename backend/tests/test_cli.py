from __future__ import annotations

from typer.testing import CliRunner

from app.cli.main import app

runner = CliRunner()


def _invoke(*args: str):
    return runner.invoke(app, list(args))


def test_validate_ok():
    result = _invoke("validate", "hermit", "fool", "justice")
    assert result.exit_code == 0
    assert "OK" in result.output


def test_validate_rejects_bad_sequence():
    result = _invoke("validate", "hermit", "fool")
    assert result.exit_code == 1
    assert "last archetype" in result.output


def test_compose_create_list_export():
    created = _invoke("compose", "create", "cli-suite", "hermit", "chariot", "justice")
    assert created.exit_code == 0
    assert "Composição criada" in created.output

    listing = _invoke("compose", "list")
    assert listing.exit_code == 0
    assert "hermit → chariot → justice" in listing.output

    exported = _invoke("compose", "export", "1", "--fmt", "yaml")
    assert exported.exit_code == 0
    assert "hermit" in exported.output


def test_compose_create_rejects_duplicates():
    result = _invoke("compose", "create", "dupe", "hermit", "hermit", "justice")
    assert result.exit_code == 1
    assert "must not repeat" in result.output


def test_compose_get_not_found():
    result = _invoke("compose", "get", "99999")
    assert result.exit_code == 1


def test_export_serializers():
    from app.services.export import serialize

    data = {"composition": {"id": 1, "name": "x"}}
    assert "id: 1" in serialize(data, "yaml")
    assert '"name": "x"' in serialize(data, "json")
    assert "id" in serialize(data, "json")


def _seed_pending_run(kind: str = "finding_review", next_agent: str = "human_gate") -> int:
    import asyncio

    from app.db.models import Run
    from app.db.session import async_session_factory
    from app.orchestration.state import GraphState

    state = GraphState(
        target={"name": "example.com"},
        findings=[
            {
                "id": "F-1",
                "title": "Signal from source for example.com",
                "confidence": 0.4,
                "status": "candidate",
                "requires_human_review": True,
            }
        ],
        pending_review={
            "id": "review-1",
            "kind": kind,
            "context": "Review candidate finding.",
            "proposal": {"id": "F-1"},
            "created_at": "2026-01-01T00:00:00+00:00",
        },
        next_agent=next_agent,
        human_gate_next="justice" if kind == "finding_review" else None,
    )

    async def _create() -> int:
        async with async_session_factory() as session:
            run = Run(status="pending_review", result=state.model_dump())
            session.add(run)
            await session.commit()
            await session.refresh(run)
            return run.id

    return asyncio.run(_create())


def test_compose_pending_empty():
    result = _invoke("compose", "pending")
    assert result.exit_code == 0
    assert "Nenhum run" in result.output


def test_compose_pending_lists_review():
    run_id = _seed_pending_run()
    result = _invoke("compose", "pending")
    assert result.exit_code == 0
    assert str(run_id) in result.output
    assert "finding_review" in result.output


def test_compose_review_approves_and_completes():
    import asyncio

    from app.db.models import Run
    from app.db.session import async_session_factory

    run_id = _seed_pending_run()
    result = _invoke("compose", "review", str(run_id), "--approve", "--yes")
    assert result.exit_code == 0
    assert "completed" in result.output

    async def _check() -> str:
        async with async_session_factory() as session:
            run = await session.get(Run, run_id)
            return run.status

    assert asyncio.run(_check()) == "completed"


def test_compose_review_requires_one_flag():
    run_id = _seed_pending_run()
    result = _invoke("compose", "review", str(run_id))
    assert result.exit_code == 1
    assert "--approve" in result.output


def test_compose_review_rejects_unknown_run():
    result = _invoke("compose", "review", "99999", "--approve", "--yes")
    assert result.exit_code == 1
