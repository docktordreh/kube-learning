"""Practice-lab lifecycle: start, status, hint, check, solution, reset, stop."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel

from cka_labs import paths, proc
from cka_labs.backends import Cluster, get_backend
from cka_labs.engine import catalog
from cka_labs.engine.catalog import LabSource
from cka_labs.engine.evaluator import CheckResult, evaluate_all
from cka_labs.engine.generator import new_seed
from cka_labs.engine.progress import Progress
from cka_labs.engine.runner import Runner, SetupError
from cka_labs.errors import CkaError
from cka_labs.models import Lab

Log = Callable[[str], None]


class ActiveLab(BaseModel):
    lab_id: str
    backend: str
    cluster: str
    seed: int
    values: dict[str, str]
    captured: dict[str, str] = {}
    started_at: float
    hints_used: int = 0
    solution_viewed: bool = False
    solved: bool = False
    attempt_id: int


def session_file() -> Path:
    return paths.state_dir() / "lab.json"


def load_session() -> ActiveLab | None:
    path = session_file()
    if not path.is_file():
        return None
    return ActiveLab.model_validate_json(path.read_text())


def save_session(session: ActiveLab) -> None:
    paths.ensure(paths.state_dir())
    session_file().write_text(session.model_dump_json(indent=2))


def clear_session() -> None:
    session_file().unlink(missing_ok=True)


def exam_active() -> bool:
    return (paths.state_dir() / "exam.json").is_file()


def find_cluster(backend_name: str, cluster_name: str) -> Cluster:
    backend = get_backend(backend_name)
    main = backend.main()
    if main.name == cluster_name:
        return main
    for index in range(1, backend.max_extra_clusters + 1):
        extra = backend.extra(index)
        if extra.name == cluster_name:
            return extra
    raise CkaError(f"unknown cluster {cluster_name} for backend {backend_name}")


@dataclass
class Prepared:
    source: LabSource
    lab: Lab
    runner: Runner
    values: dict[str, str]


def prepare(source: LabSource, cluster: Cluster, seed: int, log: Log, captured: dict[str, str] | None = None) -> Prepared:
    values = source.values(seed, cluster.nodes())
    lab = source.load(values)
    if cluster.backend_name not in lab.backends:
        raise CkaError(
            f"{lab.id} is not supported on the {cluster.backend_name} backend (supported: {', '.join(lab.backends)})"
        )
    runner = Runner(cluster, source, lab, values, log=log, captured=dict(captured or {}))
    return Prepared(source, lab, runner, values)


def provision(prepared: Prepared, log: Log, *, preflight: bool = True) -> None:
    """Clean leftovers, set up, inject the fault and verify the broken state."""
    runner = prepared.runner
    if preflight:
        runner.ensure_clean_start()
    log(f"cleaning any leftovers of {prepared.lab.id}")
    runner.cleanup()
    log("setting up scenario")
    try:
        runner.setup()
        runner.verify_initial_state()
    except (SetupError, CkaError):
        log("setup failed; cleaning up")
        runner.cleanup()
        raise


class LabService:
    def __init__(self, progress: Progress | None = None, log: Log = print) -> None:
        self.progress = progress or Progress()
        self.log = log

    # --- helpers --------------------------------------------------------------------------

    def _require_no_exam(self) -> None:
        if exam_active():
            raise CkaError("an exam is in progress; use `cka exam ...` (or `cka exam abort`)")

    def require_session(self) -> ActiveLab:
        session = load_session()
        if session is None:
            raise CkaError("no active lab; start one with `cka lab start [LAB_ID]`")
        return session

    def _prepared(self, session: ActiveLab) -> Prepared:
        cluster = find_cluster(session.backend, session.cluster)
        return prepare(catalog.get(session.lab_id), cluster, session.seed, self.log, session.captured)

    # --- commands -------------------------------------------------------------------------

    def start(self, lab_id: str, backend_name: str, seed: int | None = None) -> tuple[ActiveLab, Lab]:
        self._require_no_exam()
        if load_session() is not None:
            self.log("stopping the currently active lab first")
            self.stop()
        backend = get_backend(backend_name)
        problems = backend.problems()
        if problems:
            raise CkaError("backend not ready:\n  " + "\n  ".join(problems))
        source = catalog.get(lab_id)
        meta = source.meta()
        if backend_name not in meta.backends:
            raise CkaError(f"{lab_id} needs one of the backends: {', '.join(meta.backends)} (use --backend)")
        if meta.isolation == "cluster":
            if backend.max_extra_clusters:
                cluster = backend.extra(1)
            elif backend.main_is_dedicated:
                cluster = backend.main()
            else:
                raise CkaError(f"{lab_id} requires an isolated cluster unavailable on {backend_name}")
        else:
            cluster = backend.main()
        self.log(f"ensuring {backend_name} cluster {cluster.name} (first run takes a few minutes)")
        cluster.ensure()
        seed = seed if seed is not None else new_seed()
        prepared = prepare(source, cluster, seed, self.log)
        provision(prepared, self.log)
        lab = prepared.lab
        session = ActiveLab(
            lab_id=lab.id,
            backend=backend_name,
            cluster=cluster.name,
            seed=seed,
            values=prepared.values,
            captured=prepared.runner.captured,
            started_at=time.time(),
            attempt_id=self._start_attempt(lab, backend_name, seed),
        )
        save_session(session)
        return session, lab

    def _start_attempt(self, lab: Lab, backend_name: str, seed: int) -> int:
        return self.progress.start_attempt(
            lab_id=lab.id,
            mode="practice",
            backend=backend_name,
            seed=seed,
            domain=lab.domain,
            objectives=lab.objectives,
            difficulty=lab.difficulty,
            hints_total=len(lab.hints),
            estimated_minutes=lab.estimated_minutes,
        )

    def task(self, session: ActiveLab) -> str:
        return catalog.get(session.lab_id).read("task.md", session.values)

    def lab(self, session: ActiveLab) -> Lab:
        return catalog.get(session.lab_id).load(session.values)

    def check(self) -> tuple[ActiveLab, list[CheckResult]]:
        self._require_no_exam()
        session = self.require_session()
        prepared = self._prepared(session)
        results = evaluate_all(prepared.lab.checks, prepared.runner.context(), settle=True)
        passed = all(r.passed for r in results)
        if not session.solved:
            self.progress.record_check(session.attempt_id, [r.id for r in results if not r.passed])
            if passed:
                self.progress.finish_attempt(session.attempt_id, "passed")
                session = session.model_copy(update={"solved": True})
                save_session(session)
        return session, results

    def hint(self) -> tuple[int, int, str]:
        self._require_no_exam()
        session = self.require_session()
        hints = self.lab(session).hints
        if session.hints_used >= len(hints):
            return len(hints), len(hints), hints[-1]
        index = session.hints_used
        if not session.solved:
            self.progress.record_hint(session.attempt_id)
        save_session(session.model_copy(update={"hints_used": index + 1}))
        return index + 1, len(hints), hints[index]

    def solution(self) -> tuple[str, str]:
        self._require_no_exam()
        session = self.require_session()
        source = catalog.get(session.lab_id)
        if not session.solved:
            self.progress.record_solution_viewed(session.attempt_id)
        save_session(session.model_copy(update={"solution_viewed": True}))
        return source.read("solution.sh", session.values), self.explanation(session)

    def explanation(self, session: ActiveLab) -> str:
        source = catalog.get(session.lab_id)
        return source.read("explanation.md", session.values) if source.has("explanation.md") else ""

    def reset(self) -> ActiveLab:
        """Re-provision the scenario. Unsolved: same attempt, timer keeps running.
        Solved: the passed attempt is final, so the replay is a fresh attempt."""
        self._require_no_exam()
        session = self.require_session()
        prepared = self._prepared(session)
        prepared.runner.captured.clear()
        provision(prepared, self.log, preflight=False)
        update: dict[str, object] = {"captured": prepared.runner.captured, "solved": False}
        if session.solved:
            update |= {
                "attempt_id": self._start_attempt(prepared.lab, session.backend, session.seed),
                "started_at": time.time(),
                "hints_used": 0,
                "solution_viewed": False,
            }
        session = session.model_copy(update=update)
        save_session(session)
        return session

    def stop(self) -> None:
        self._require_no_exam()
        session = self.require_session()
        prepared = self._prepared(session)
        self.log(f"cleaning up {session.lab_id}")
        prepared.runner.cleanup()
        if not session.solved:
            self.progress.abandon_attempt(session.attempt_id)
        clear_session()

    def solve_reference(self) -> None:
        """Run the reference solution against the active lab (authoring/verification aid)."""
        session = self.require_session()
        prepared = self._prepared(session)
        script = prepared.source.read("solution.sh", session.values)
        # No pipefail: solutions contain diagnostic pipes (`| grep | head`); grading verifies the outcome.
        result = proc.run(["bash", "-eu", "-c", script], env=prepared.runner.script_env(), timeout=900)
        if not result.ok:
            raise CkaError(f"reference solution failed ({result.returncode}):\n{result.output()[-2000:]}")
        if not session.solved:
            self.progress.record_solution_viewed(session.attempt_id)
        save_session(session.model_copy(update={"solution_viewed": True}))
