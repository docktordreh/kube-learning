"""CLI commands that need no cluster."""

import json

from typer.testing import CliRunner

from cka_labs.cli import app
from cka_labs.engine.progress import Progress

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


def _failed_attempt() -> None:
    progress = Progress()
    attempt = progress.start_attempt(
        lab_id="networking-001", mode="practice", backend="kind", seed=1, domain="cka/networking",
        objectives=["cka/networking/services"], difficulty=1, hints_total=3, estimated_minutes=5,
    )
    progress.record_check(attempt, ["traffic"])
    progress.finish_attempt(attempt, "failed")


def test_progress_shows_readiness_and_check_descriptions() -> None:
    _failed_attempt()
    result = runner.invoke(app, ["progress"], env={"COLUMNS": "250"})
    assert result.exit_code == 0, result.output
    assert "CKA exam readiness: 0%" in result.output
    assert "HTTP via the Service DNS name reaches nginx" in result.output


def test_progress_lab_history() -> None:
    _failed_attempt()
    result = runner.invoke(app, ["progress", "networking-001"], env={"COLUMNS": "250"})
    assert result.exit_code == 0, result.output
    assert "failed" in result.output
    assert "traffic" in result.output
    exported = json.loads(runner.invoke(app, ["progress", "networking-001", "--json"]).output)
    assert exported[0]["failed_checks"] == {"traffic": 1}


def test_progress_unknown_lab_fails() -> None:
    result = runner.invoke(app, ["progress", "nope-001"])
    assert result.exit_code != 0


def test_lab_commands_without_session_fail_cleanly() -> None:
    for command in (["lab", "check"], ["lab", "hint"], ["lab", "status"]):
        result = runner.invoke(app, command)
        assert result.exit_code != 0
        assert "no active lab" in str(result.exception)


def test_lab_list_filters_by_certification() -> None:
    result = runner.invoke(app, ["lab", "list", "--cert", "ckad"], env={"COLUMNS": "250"})
    assert result.exit_code == 0, result.output
    assert "networking-001" in result.output
    assert "troubleshooting-007" not in result.output  # CKA-only node lab


def test_progress_per_certification() -> None:
    result = runner.invoke(app, ["progress", "--cert", "ckad"], env={"COLUMNS": "250"})
    assert result.exit_code == 0, result.output
    assert "Application Design and Build (20%)" in result.output


def test_unknown_certification_fails() -> None:
    result = runner.invoke(app, ["practice", "--cert", "nope", "--dry-run"])
    assert result.exit_code != 0
    assert "unknown certification" in str(result.exception)


def test_explicit_lab_must_match_certification() -> None:
    result = runner.invoke(app, ["lab", "start", "troubleshooting-007", "--cert", "ckad"])
    assert result.exit_code != 0
    assert "does not count toward" in str(result.exception)


def test_practice_dry_run_recommends_fundamentals() -> None:
    result = runner.invoke(app, ["practice", "--dry-run"], env={"COLUMNS": "200"})
    assert result.exit_code == 0, result.output
    assert "why:" in result.output


def test_image_load_needs_names_or_an_archive() -> None:
    for args in (["image", "load"], ["image", "load", "x:1", "--archive", "x.tar"]):
        result = runner.invoke(app, args)
        assert result.exit_code != 0
        assert "not both" in str(result.exception)
