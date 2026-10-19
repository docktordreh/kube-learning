"""Progress tracking in SQLite (stdlib only).

An *attempt* is one lab session (start -> solved/abandoned). Objective weakness is
    weakness = 1 - (clean_passes + 1) / (attempts + 2)
i.e. a Laplace-smoothed failure rate: 0.5 for an untried objective, falling toward 0 as
clean passes accumulate. A pass after viewing the solution does not count as clean.
"""

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from cka_labs import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS attempts (
    id INTEGER PRIMARY KEY,
    lab_id TEXT NOT NULL,
    mode TEXT NOT NULL,              -- practice | exam
    backend TEXT NOT NULL,
    seed INTEGER NOT NULL,
    domain TEXT NOT NULL,
    objectives TEXT NOT NULL,        -- JSON list
    difficulty INTEGER NOT NULL,
    started_at REAL NOT NULL,
    ended_at REAL,
    status TEXT NOT NULL,            -- active | passed | failed | abandoned
    hints_used INTEGER NOT NULL DEFAULT 0,
    solution_viewed INTEGER NOT NULL DEFAULT 0,
    checks_run INTEGER NOT NULL DEFAULT 0,
    exam_id INTEGER
);
CREATE TABLE IF NOT EXISTS check_failures (
    attempt_id INTEGER NOT NULL REFERENCES attempts(id),
    check_id TEXT NOT NULL,
    count INTEGER NOT NULL,
    PRIMARY KEY (attempt_id, check_id)
);
CREATE TABLE IF NOT EXISTS exams (
    id INTEGER PRIMARY KEY,
    backend TEXT NOT NULL,
    seed INTEGER NOT NULL,
    started_at REAL NOT NULL,
    duration_minutes INTEGER NOT NULL,
    submitted_at REAL,
    score REAL,
    max_score REAL,
    pass_percent INTEGER NOT NULL,
    report TEXT                      -- JSON
);
"""


@dataclass(frozen=True)
class ObjectiveStats:
    objective: str
    attempts: int
    clean_passes: int
    passes: int
    hints: int
    avg_minutes: float | None

    @property
    def weakness(self) -> float:
        return 1 - (self.clean_passes + 1) / (self.attempts + 2)


@dataclass(frozen=True)
class LabStats:
    lab_id: str
    attempts: int
    clean_passes: int
    last_attempt: float | None


class Progress:
    def __init__(self, db: Path | None = None) -> None:
        self.db = db or paths.progress_db()
        paths.ensure(self.db.parent)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # --- attempts -------------------------------------------------------------------------

    def start_attempt(
        self,
        *,
        lab_id: str,
        mode: str,
        backend: str,
        seed: int,
        domain: str,
        objectives: list[str],
        difficulty: int,
        exam_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO attempts (lab_id, mode, backend, seed, domain, objectives, difficulty, started_at, status,"
                " exam_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?)",
                (lab_id, mode, backend, seed, domain, json.dumps(objectives), difficulty, time.time(), exam_id),
            )
            return cursor.lastrowid or 0

    def record_check(self, attempt_id: int, failed_check_ids: list[str]) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE attempts SET checks_run = checks_run + 1 WHERE id = ?", (attempt_id,))
            for check_id in failed_check_ids:
                conn.execute(
                    "INSERT INTO check_failures (attempt_id, check_id, count) VALUES (?, ?, 1)"
                    " ON CONFLICT(attempt_id, check_id) DO UPDATE SET count = count + 1",
                    (attempt_id, check_id),
                )

    def record_hint(self, attempt_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE attempts SET hints_used = hints_used + 1 WHERE id = ?", (attempt_id,))

    def record_solution_viewed(self, attempt_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE attempts SET solution_viewed = 1 WHERE id = ?", (attempt_id,))

    def finish_attempt(self, attempt_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE attempts SET status = ?, ended_at = ? WHERE id = ? AND status = 'active'",
                (status, time.time(), attempt_id),
            )

    # --- statistics -----------------------------------------------------------------------

    def objective_stats(self) -> dict[str, ObjectiveStats]:
        totals: dict[str, dict[str, float]] = {}
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM attempts WHERE status != 'active'").fetchall()
        for row in rows:
            clean = row["status"] == "passed" and not row["solution_viewed"]
            loaded: object = json.loads(row["objectives"])
            objectives = [o for o in loaded if isinstance(o, str)] if isinstance(loaded, list) else []
            for objective in objectives:
                t = totals.setdefault(objective, {"attempts": 0, "clean": 0, "passes": 0, "hints": 0, "secs": 0.0})
                t["attempts"] += 1
                t["clean"] += int(clean)
                t["hints"] += row["hints_used"]
                if row["status"] == "passed":
                    t["passes"] += 1
                    t["secs"] += (row["ended_at"] or row["started_at"]) - row["started_at"]
        return {
            objective: ObjectiveStats(
                objective=objective,
                attempts=int(t["attempts"]),
                clean_passes=int(t["clean"]),
                passes=int(t["passes"]),
                hints=int(t["hints"]),
                avg_minutes=(t["secs"] / t["passes"] / 60) if t["passes"] else None,
            )
            for objective, t in totals.items()
        }

    def lab_stats(self) -> dict[str, LabStats]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT lab_id, COUNT(*) AS attempts,"
                " SUM(CASE WHEN status = 'passed' AND solution_viewed = 0 THEN 1 ELSE 0 END) AS clean,"
                " MAX(started_at) AS last FROM attempts WHERE status != 'active' GROUP BY lab_id"
            ).fetchall()
        return {r["lab_id"]: LabStats(r["lab_id"], r["attempts"], r["clean"] or 0, r["last"]) for r in rows}

    def top_failed_checks(self, limit: int = 10) -> list[tuple[str, str, int]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.lab_id, f.check_id, SUM(f.count) AS n FROM check_failures f"
                " JOIN attempts a ON a.id = f.attempt_id GROUP BY a.lab_id, f.check_id ORDER BY n DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [(r["lab_id"], r["check_id"], r["n"]) for r in rows]

    # --- exams ----------------------------------------------------------------------------

    def start_exam(self, *, backend: str, seed: int, duration_minutes: int, pass_percent: int) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO exams (backend, seed, started_at, duration_minutes, pass_percent) VALUES (?, ?, ?, ?, ?)",
                (backend, seed, time.time(), duration_minutes, pass_percent),
            )
            return cursor.lastrowid or 0

    def finish_exam(self, exam_id: int, score: float, max_score: float, report: object) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE exams SET submitted_at = ?, score = ?, max_score = ?, report = ? WHERE id = ?",
                (time.time(), score, max_score, json.dumps(report), exam_id),
            )

    def exam_report(self, exam_id: int | None = None) -> dict[str, object] | None:
        with self._connect() as conn:
            if exam_id is None:
                row = conn.execute(
                    "SELECT * FROM exams WHERE submitted_at IS NOT NULL ORDER BY id DESC LIMIT 1"
                ).fetchone()
            else:
                row = conn.execute("SELECT * FROM exams WHERE id = ?", (exam_id,)).fetchone()
        if row is None or row["report"] is None:
            return None
        loaded: object = json.loads(row["report"])
        return loaded if isinstance(loaded, dict) else None

    def exams(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, started_at, submitted_at, score, max_score, pass_percent FROM exams ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    # --- export ---------------------------------------------------------------------------

    def export(self) -> dict[str, object]:
        with self._connect() as conn:
            attempts = [dict(r) for r in conn.execute("SELECT * FROM attempts ORDER BY id").fetchall()]
            failures = [dict(r) for r in conn.execute("SELECT * FROM check_failures").fetchall()]
        return {
            "attempts": attempts,
            "check_failures": failures,
            "exams": self.exams(),
            "objectives": {k: {**asdict(v), "weakness": round(v.weakness, 3)} for k, v in self.objective_stats().items()},
        }
