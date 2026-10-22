import sqlite3
from pathlib import Path

import pytest

from cka_labs.engine.progress import HALF_LIFE_DAYS, MIGRATIONS, SCHEMA, Progress
from cka_labs.errors import CkaError

DAY = 86400.0


def _attempt(progress: Progress, lab: str, objectives: list[str]) -> int:
    return progress.start_attempt(
        lab_id=lab, mode="practice", backend="kind", seed=1, domain="networking", objectives=objectives, difficulty=2,
        hints_total=3, estimated_minutes=5,
    )


def _version(db: Path) -> int:
    with sqlite3.connect(db) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def test_new_database_is_at_latest_version(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    progress = Progress(db)
    assert _version(db) == len(MIGRATIONS)
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    row = progress.export()["attempts"][0]  # type: ignore[index]
    assert (row["id"], row["hints_total"], row["estimated_minutes"]) == (attempt, 3, 5)


def test_legacy_database_is_migrated_in_place(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO attempts (lab_id, mode, backend, seed, domain, objectives, difficulty, started_at, status)"
            " VALUES ('networking-001', 'practice', 'kind', 1, 'networking', '[\"networking/services\"]', 2, 0, 'passed')"
        )
    progress = Progress(db)
    assert _version(db) == len(MIGRATIONS)
    assert progress.lab_stats()["networking-001"].clean_passes == 1
    row = progress.export()["attempts"][0]  # type: ignore[index]
    assert (row["hints_total"], row["estimated_minutes"]) == (None, None)
    Progress(db)  # reopening is a no-op
    assert _version(db) == len(MIGRATIONS)


def test_newer_database_is_refused(tmp_path: Path) -> None:
    db = tmp_path / "p.db"
    with sqlite3.connect(db) as conn:
        conn.execute(f"PRAGMA user_version = {len(MIGRATIONS) + 1}")
    with pytest.raises(CkaError, match="newer"):
        Progress(db)


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
    assert abs(stats.weakness - 0.6) < 1e-6


def test_solution_viewed_is_not_clean(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.record_solution_viewed(attempt)
    progress.finish_attempt(attempt, "passed")
    stats = progress.objective_stats()["networking/services"]
    assert (stats.passes, stats.clean_passes, stats.credit) == (1, 0, 0.0)


def test_hints_reduce_credit(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    assisted = _attempt(progress, "networking-001", ["networking/services"])
    for _ in range(3):  # all 3 of 3 hints
        progress.record_hint(assisted)
    progress.finish_attempt(assisted, "passed")
    unassisted = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(unassisted, "passed")
    stats = progress.objective_stats()["networking/services"]
    assert (stats.clean_passes, stats.credit) == (2, 1.5)
    # 1 - (1.5 credit + 1) / (2 attempts + 2)
    assert abs(stats.weakness - 0.375) < 1e-6


def test_legacy_hinted_pass_assumes_all_hints_used(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.record_hint(attempt)
    progress.finish_attempt(attempt, "passed")
    with sqlite3.connect(progress.db) as conn:
        conn.execute("UPDATE attempts SET hints_total = NULL")
    assert progress.objective_stats()["networking/services"].credit == 0.5


def _set_times(progress: Progress, attempt: int, started_at: float, ended_at: float) -> None:
    with sqlite3.connect(progress.db) as conn:
        conn.execute("UPDATE attempts SET started_at = ?, ended_at = ? WHERE id = ?", (started_at, ended_at, attempt))


def test_old_results_fade(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(attempt, "passed")
    now = 100 * DAY
    _set_times(progress, attempt, now - HALF_LIFE_DAYS * DAY - 60, now - HALF_LIFE_DAYS * DAY)
    stats = progress.objective_stats(now=now)["networking/services"]
    assert (stats.attempts, stats.credit) == (1, 1.0)
    assert abs(stats.weight - 0.5) < 1e-9
    # 1 - (0.5 weighted credit + 1) / (0.5 weight + 2)
    assert abs(stats.weakness - 0.4) < 1e-9
    forgotten = progress.objective_stats(now=now + 50 * HALF_LIFE_DAYS * DAY)["networking/services"]
    assert abs(forgotten.weakness - 0.5) < 1e-9  # back to untried


def test_pace_is_time_over_target_for_passes(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    fast = _attempt(progress, "networking-001", ["networking/services"])  # target 5 min
    progress.finish_attempt(fast, "passed")
    _set_times(progress, fast, 0, 5 * 60)
    slow = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(slow, "passed")
    _set_times(progress, slow, 0, 15 * 60)
    failed = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(failed, "failed")
    _set_times(progress, failed, 0, 60 * 60)
    assert progress.objective_stats()["networking/services"].pace == 2.0  # mean of 1x and 3x


def test_pace_is_unknown_without_target(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(attempt, "passed")
    with sqlite3.connect(progress.db) as conn:
        conn.execute("UPDATE attempts SET estimated_minutes = NULL")
    stats = progress.objective_stats()["networking/services"]
    assert stats.pace is None
    assert stats.avg_minutes is not None


def test_quick_stop_without_engagement_is_cancelled(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.abandon_attempt(attempt)
    assert progress.export()["attempts"][0]["status"] == "cancelled"  # type: ignore[index]
    assert progress.objective_stats() == {}
    assert progress.lab_stats() == {}


def test_engaged_or_long_stop_is_abandoned(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    checked = _attempt(progress, "networking-001", ["networking/services"])
    progress.record_check(checked, ["traffic"])
    hinted = _attempt(progress, "networking-001", ["networking/services"])
    progress.record_hint(hinted)
    idle = _attempt(progress, "networking-001", ["networking/services"])
    with sqlite3.connect(progress.db) as conn:
        conn.execute("UPDATE attempts SET started_at = started_at - 300 WHERE id = ?", (idle,))
    for attempt in (checked, hinted, idle):
        progress.abandon_attempt(attempt)
    assert progress.objective_stats()["networking/services"].attempts == 3


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


def test_finished_attempt_is_immutable(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(attempt, "passed")
    progress.record_check(attempt, ["traffic"])
    progress.record_hint(attempt)
    progress.record_solution_viewed(attempt)
    stats = progress.objective_stats()["networking/services"]
    assert (stats.clean_passes, stats.hints) == (1, 0)
    assert progress.top_failed_checks() == []


def test_export_is_json_serialisable(tmp_path: Path) -> None:
    import json

    progress = Progress(tmp_path / "p.db")
    attempt = _attempt(progress, "networking-001", ["networking/services"])
    progress.finish_attempt(attempt, "passed")
    exported = json.loads(json.dumps(progress.export()))
    assert exported["objectives"]["networking/services"]["clean_passes"] == 1
