"""CLI commands that need no cluster."""

import json

from typer.testing import CliRunner

from cka_labs.cli import app

runner = CliRunner()


def test_lab_list() -> None:
    result = runner.invoke(app, ["lab", "list"], env={"COLUMNS": "200"})
    assert result.exit_code == 0
    assert "networking-001" in result.output


def test_dev_validate() -> None:
    result = runner.invoke(app, ["dev", "validate"])
    assert result.exit_code == 0, result.output


def test_progress_json_empty() -> None:
    result = runner.invoke(app, ["progress", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["attempts"] == []


def test_lab_commands_without_session_fail_cleanly() -> None:
    for command in (["lab", "check"], ["lab", "hint"], ["lab", "status"]):
        result = runner.invoke(app, command)
        assert result.exit_code != 0
        assert "no active lab" in str(result.exception)


def test_practice_dry_run_recommends_fundamentals() -> None:
    result = runner.invoke(app, ["practice", "--dry-run"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "why:" in result.output
