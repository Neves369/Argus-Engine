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
