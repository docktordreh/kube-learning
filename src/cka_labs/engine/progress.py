"""Progress tracking in SQLite (stdlib only).

An *attempt* is one lab session (start -> solved/abandoned). Objective weakness is
    weakness = 1 - (sum(w * credit) + 1) / (sum(w) + 2),  w = 0.5 ** (age_days / HALF_LIFE_DAYS)
i.e. a recency-weighted, Laplace-smoothed failure rate: 0.5 for an untried objective, falling
toward 0 as recent credit accumulates and drifting back to 0.5 as results age.
A pass earns 1 - HINT_PENALTY * hints_used / hints_total; a failure or a pass after viewing
the solution earns 0. A pass without viewing the solution is *clean*.
Pace is the mean of (time to pass / lab target time) over passes; it is informational only.
Mastery = max(0, 1 - 2 * weakness); readiness of a set of objectives is their mean mastery.
Stopping a practice lab within CANCEL_SECONDS without any check, hint or solution view
marks the attempt *cancelled*; cancelled attempts are not counted.
"""

import json
import sqlite3
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from cka_labs import paths
from cka_labs.errors import CkaError

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
    status TEXT NOT NULL,            -- active | passed | failed | abandoned | cancelled
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

# Schema version N (PRAGMA user_version) = SCHEMA plus MIGRATIONS[:N]. Append only; never edit
# a released entry. Each migration runs in one transaction together with its version bump.
MIGRATIONS: list[tuple[str, ...]] = [
    # 1: lab metadata at attempt time, for hint-weighted credit and time-vs-target (NULL for older rows)
    (
        "ALTER TABLE attempts ADD COLUMN hints_total INTEGER",
        "ALTER TABLE attempts ADD COLUMN estimated_minutes INTEGER",
    ),
    # 2: whether a check failed on the attempt's first check run (NULL for older rows)
    ("ALTER TABLE check_failures ADD COLUMN failed_first INTEGER",),
]


HINT_PENALTY = 0.5  # credit lost when every hint was revealed
CANCEL_SECONDS = 120
HALF_LIFE_DAYS = 21
COUNTED = "status IN ('passed', 'failed', 'abandoned')"


def _credit(row: sqlite3.Row) -> float:
    if row["status"] != "passed" or row["solution_viewed"]:
        return 0.0
    # hints_total is NULL before schema v1: assume a hinted pass used every hint.
    total = row["hints_total"] or row["hints_used"]
    return 1 - HINT_PENALTY * min(row["hints_used"] / total, 1) if total else 1.0


@dataclass(frozen=True)
class ObjectiveStats:
    objective: str
    attempts: int
    clean_passes: int
    credit: float
    weight: float  # sum of recency weights
    weighted_credit: float
    passes: int
    hints: int
    avg_minutes: float | None
    pace: float | None  # mean time-to-pass / target; None without a recorded target

    @property
    def weakness(self) -> float:
        return 1 - (self.weighted_credit + 1) / (self.weight + 2)

    @property
    def mastery(self) -> float:
        """Net evidence of success in [0, 1]: 0 when untried or failing half the time, toward 1
        as recent credit accumulates. Equals max(0, 1 - 2 * weakness)."""
        return max(0.0, 1 - 2 * self.weakness)


def readiness(stats: dict[str, ObjectiveStats], objectives: list[str]) -> float:
    """Mean mastery over objectives; untried objectives count as 0."""
    if not objectives:
        return 0.0
    return sum(stats[o].mastery if o in stats else 0.0 for o in objectives) / len(objectives)


@dataclass(frozen=True)
class FailedCheck:
    lab_id: str
    check_id: str
    first_try: int  # attempts where it failed on the first check run (a knowledge gap)
    attempts: int  # attempts where it failed at all
    runs: int  # check runs where it failed (includes iteration)


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
        self._migrate()

    def _migrate(self) -> None:
        conn = sqlite3.connect(self.db, isolation_level=None)  # explicit transactions: ALTER must not autocommit
        try:
            for target, statements in enumerate(MIGRATIONS, 1):
                conn.execute("BEGIN IMMEDIATE")  # re-read the version under the write lock (concurrent cka runs)
                version = conn.execute("PRAGMA user_version").fetchone()[0]
                if version >= target:
                    conn.execute("COMMIT")
                    continue
                try:
                    for statement in statements:
                        conn.execute(statement)
                    conn.execute(f"PRAGMA user_version = {target}")
                    conn.execute("COMMIT")
                except BaseException:
                    conn.execute("ROLLBACK")
                    raise
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            if version > len(MIGRATIONS):
                raise CkaError(
                    f"{self.db} has schema version {version}, newer than this cka supports ({len(MIGRATIONS)}); "
                    "upgrade cka"
                )
        finally:
            conn.close()

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
        hints_total: int,
        estimated_minutes: int,
        exam_id: int | None = None,
    ) -> int:
        with self._connect() as conn:
            cursor = conn.execute(
                "INSERT INTO attempts (lab_id, mode, backend, seed, domain, objectives, difficulty, started_at, status,"
                " exam_id, hints_total, estimated_minutes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                (
                    lab_id, mode, backend, seed, domain, json.dumps(objectives), difficulty, time.time(), exam_id,
                    hints_total, estimated_minutes,
                ),
            )
            return cursor.lastrowid or 0

    # Finished attempts are immutable: every mutator only touches status = 'active'.

    def record_check(self, attempt_id: int, failed_check_ids: list[str]) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "UPDATE attempts SET checks_run = checks_run + 1 WHERE id = ? AND status = 'active' RETURNING checks_run",
                (attempt_id,),
            ).fetchone()
            if row is None:
                return
            first = int(row[0] == 1)
            for check_id in failed_check_ids:
                conn.execute(
                    "INSERT INTO check_failures (attempt_id, check_id, count, failed_first) VALUES (?, ?, 1, ?)"
                    " ON CONFLICT(attempt_id, check_id) DO UPDATE SET count = count + 1",
                    (attempt_id, check_id, first),
                )

    def record_hint(self, attempt_id: int) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE attempts SET hints_used = hints_used + 1 WHERE id = ? AND status = 'active'", (attempt_id,)
            )

    def record_solution_viewed(self, attempt_id: int) -> None:
        with self._connect() as conn:
            conn.execute("UPDATE attempts SET solution_viewed = 1 WHERE id = ? AND status = 'active'", (attempt_id,))

    def finish_attempt(self, attempt_id: int, status: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE attempts SET status = ?, ended_at = ? WHERE id = ? AND status = 'active'",
                (status, time.time(), attempt_id),
            )

    def abandon_attempt(self, attempt_id: int) -> None:
        """Practice stop before passing; an unengaged quick start-stop becomes 'cancelled'."""
        now = time.time()
        with self._connect() as conn:
            conn.execute(
                "UPDATE attempts SET ended_at = ?, status = CASE"
                " WHEN checks_run = 0 AND hints_used = 0 AND solution_viewed = 0 AND ? - started_at < ?"
                " THEN 'cancelled' ELSE 'abandoned' END"
                " WHERE id = ? AND status = 'active'",
                (now, now, CANCEL_SECONDS, attempt_id),
            )

    # --- statistics -----------------------------------------------------------------------

    def objective_stats(self, now: float | None = None) -> dict[str, ObjectiveStats]:
        now = time.time() if now is None else now
        keys = ("attempts", "clean", "credit", "weight", "weighted", "passes", "hints", "secs", "paced", "pace")
        totals: dict[str, dict[str, float]] = {}
        with self._connect() as conn:
            rows = conn.execute(f"SELECT * FROM attempts WHERE {COUNTED}").fetchall()
        for row in rows:
            clean = row["status"] == "passed" and not row["solution_viewed"]
            credit = _credit(row)
            ended = row["ended_at"] or row["started_at"]
            weight = 0.5 ** (max(now - ended, 0) / 86400 / HALF_LIFE_DAYS)
            loaded: object = json.loads(row["objectives"])
            objectives = [o for o in loaded if isinstance(o, str)] if isinstance(loaded, list) else []
            for objective in objectives:
                t = totals.setdefault(objective, dict.fromkeys(keys, 0.0))
                t["attempts"] += 1
                t["clean"] += int(clean)
                t["credit"] += credit
                t["weight"] += weight
                t["weighted"] += weight * credit
                t["hints"] += row["hints_used"]
                if row["status"] == "passed":
                    t["passes"] += 1
                    t["secs"] += ended - row["started_at"]
                    if row["estimated_minutes"]:
                        t["paced"] += 1
                        t["pace"] += (ended - row["started_at"]) / 60 / row["estimated_minutes"]
        return {
            objective: ObjectiveStats(
                objective=objective,
                attempts=int(t["attempts"]),
                clean_passes=int(t["clean"]),
                credit=t["credit"],
                weight=t["weight"],
                weighted_credit=t["weighted"],
                passes=int(t["passes"]),
                hints=int(t["hints"]),
                avg_minutes=(t["secs"] / t["passes"] / 60) if t["passes"] else None,
                pace=(t["pace"] / t["paced"]) if t["paced"] else None,
            )
            for objective, t in totals.items()
        }

    def lab_stats(self) -> dict[str, LabStats]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT lab_id, COUNT(*) AS attempts,"
                " SUM(CASE WHEN status = 'passed' AND solution_viewed = 0 THEN 1 ELSE 0 END) AS clean,"
                f" MAX(started_at) AS last FROM attempts WHERE {COUNTED} GROUP BY lab_id"
            ).fetchall()
        return {r["lab_id"]: LabStats(r["lab_id"], r["attempts"], r["clean"] or 0, r["last"]) for r in rows}

    def top_failed_checks(self, limit: int = 10) -> list[FailedCheck]:
        """Checks ranked by first-try failures. Rows from before schema v2 count as first-try."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT a.lab_id, f.check_id, SUM(COALESCE(f.failed_first, 1)) AS first_try,"
                " COUNT(*) AS attempts, SUM(f.count) AS runs"
                " FROM check_failures f JOIN attempts a ON a.id = f.attempt_id GROUP BY a.lab_id, f.check_id"
                " ORDER BY first_try DESC, attempts DESC, runs DESC, a.lab_id, f.check_id LIMIT ?",
                (limit,),
            ).fetchall()
        return [FailedCheck(r["lab_id"], r["check_id"], r["first_try"], r["attempts"], r["runs"]) for r in rows]

    def lab_history(self, lab_id: str) -> list[dict[str, Any]]:
        """Every attempt of one lab (including active and cancelled), oldest first."""
        with self._connect() as conn:
            attempts = [dict(r) for r in conn.execute("SELECT * FROM attempts WHERE lab_id = ? ORDER BY id", (lab_id,))]
            failures = conn.execute(
                "SELECT f.attempt_id, f.check_id, f.count FROM check_failures f"
                " JOIN attempts a ON a.id = f.attempt_id WHERE a.lab_id = ? ORDER BY f.check_id",
                (lab_id,),
            ).fetchall()
        by_attempt: dict[int, dict[str, int]] = {}
        for f in failures:
            by_attempt.setdefault(f["attempt_id"], {})[f["check_id"]] = f["count"]
        return [{**a, "failed_checks": by_attempt.get(a["id"], {})} for a in attempts]

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
