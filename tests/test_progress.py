from pathlib import Path

from cka_labs.engine.progress import Progress


def _attempt(progress: Progress, lab: str, objectives: list[str]) -> int:
    return progress.start_attempt(
        lab_id=lab, mode="practice", backend="kind", seed=1, domain="networking", objectives=objectives, difficulty=2
    )


def test_attempts_persist_across_instances(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    first = Progress(db)
    attempt = _attempt(first, "networking-001", ["networking/services"])
    first.record_check(attempt, ["endpoints", "traffic"])
    first.record_check(attempt, ["traffic"])
    first.record_hint(attempt)
    first.finish_attempt(attempt, "passed")

    second = Progress(db)
    stats = second.objective_stats()["networking/services"]
    assert (stats.attempts, stats.clean_passes, stats.hints) == (1, 1, 1)
    assert second.top_failed_checks()[0] == ("networking-001", "traffic", 2)


def test_weakness_formula(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    for status in ("passed", "abandoned", "abandoned"):
        attempt = _attempt(progress, "networking-001", ["networking/services"])
        progress.finish_attempt(attempt, status)
    stats = progress.objective_stats()["networking/services"]
    # 1 - (1 clean + 1) / (3 attempts + 2)
    assert abs(stats.weakness - 0.6) < 1e-9


def test_solution_viewed_is_not_clean(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.record_solution_viewed(attempt)
    progress.finish_attempt(attempt, "passed")
    stats = progress.objective_stats()["networking/services"]
    assert (stats.passes, stats.clean_passes) == (1, 0)


def test_active_attempts_do_not_count(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    _attempt(progress, "networking-001", ["networking/services"])
    assert progress.objective_stats() == {}


def test_finish_is_idempotent(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(attempt, "passed")
    progress.finish_attempt(attempt, "abandoned")
    assert progress.lab_stats()["networking-001"].clean_passes == 1


def test_export_is_json_serialisable(tmp_path: Path) -> None:
    import json

    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(attempt, "passed")
    exported = json.loads(json.dumps(progress.export()))
    assert exported["objectives"]["networking/services"]["clean_passes"] == 1
