"""Timed mock-exam lifecycle.

An exam is deliberately boring state: a JSON session plus SQLite results. Tasks are
selected deterministically from the curriculum weights, provisioned before the timer
starts, and graded only from live state at submit time. Solutions and hints are not
reachable through this module.
"""

import hashlib
import time
from pathlib import Path
from collections.abc import Callable
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from cka_labs import paths
from cka_labs.backends import Cluster, get_backend
from cka_labs.config import DEFAULT_CERT, curriculum
from cka_labs.engine import catalog
from cka_labs.engine.evaluator import CheckResult, evaluate_all
from cka_labs.engine.generator import new_seed
from cka_labs.engine.lifecycle import Prepared, exam_active, load_session, prepare, provision
from cka_labs.engine.progress import Progress
from cka_labs.engine.runner import Runner
from cka_labs.errors import CkaError
from cka_labs.models import Lab


ExamTaskStatus = Literal["pending", "skipped", "passed", "failed"]


class ExamTask(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: int = Field(ge=1)
    lab_id: str
    domain: str
    difficulty: int
    points: int = Field(gt=0)
    backend: str
    cluster: str
    seed: int
    values: dict[str, str]
    captured: dict[str, str] = {}
    status: ExamTaskStatus = "pending"
    attempt_id: int
    last_results: list[dict[str, str | bool]] = []


class ExamState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exam_id: int
    cert: str = DEFAULT_CERT  # sessions saved before multi-certification support were CKA
    backend: str
    seed: int
    started_at: float
    duration_minutes: int
    pass_percent: int
    tasks: list[ExamTask]
    submitted_at: float | None = None
    score: float | None = None
    max_score: int | None = None


def session_file() -> Path:
    return paths.state_dir() / "exam.json"


def load_exam() -> ExamState | None:
    path = session_file()
    if not path.is_file():
        return None
    return ExamState.model_validate_json(path.read_text())


def save_exam(exam: ExamState) -> None:
    paths.ensure(paths.state_dir())
    session_file().write_text(exam.model_dump_json(indent=2))


def clear_exam() -> None:
    session_file().unlink(missing_ok=True)


def exam_kubeconfig() -> Path:
    exam = load_exam()
    if exam is None:
        raise CkaError("no active exam")
    return get_backend(exam.backend).main().kubeconfig


def elapsed(exam: ExamState) -> float:
    return max(0.0, time.time() - exam.started_at)


def remaining(exam: ExamState) -> float:
    return max(0.0, exam.duration_minutes * 60 - elapsed(exam))


def _points(difficulty: int) -> int:
    return {1: 5, 2: 10, 3: 15, 4: 20}[difficulty]


def _stable_number(seed: int, lab_id: str) -> int:
    digest = hashlib.sha256(f"{seed}:{lab_id}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def _select(labs: list[Lab], seed: int, count: int, cert: str = DEFAULT_CERT) -> list[Lab]:
    """Pick a `count`-task exam split over `cert`'s domains by weight (CKA, 8 tasks: 2/1/2/1/2).

    Each domain's quota is explicit, making the selection auditable rather than
    probabilistic. A lab counts toward its domain within `cert`. A stable hash gives a
    different exam per seed without making a session irreproducible.
    """
    quotas = curriculum(cert).quotas(count)
    grouped: dict[str, list[Lab]] = {domain: [] for domain in quotas}
    for lab in labs:
        domain = lab.domain_in(cert)
        if domain in grouped:
            grouped[domain].append(lab)
    selected: list[Lab] = []
    for domain, quota in quotas.items():
        choices = sorted(grouped[domain], key=lambda lab: (_stable_number(seed, lab.id), lab.id))
        if len(choices) < quota:
            raise CkaError(f"not enough {cert} {domain} labs for an exam (need {quota}, have {len(choices)})")
        # Keep the exam practical: every domain gets at least one level-2+ task
        # when the catalog can provide one.
        advanced = [lab for lab in choices if lab.difficulty >= 2]
        picked = advanced[:1] + [lab for lab in choices if lab not in advanced[:1]]
        selected.extend(picked[:quota])
    selected.sort(key=lambda lab: (lab.domain_in(cert) or "", lab.id))
    return selected


def _areas(lab: Lab) -> set[str]:
    areas = {f"exclusive:{area}" for area in lab.exclusive}
    areas.update(f"namespace:{namespace}" for namespace in lab.namespaces)
    areas.update(f"owned:{item}" for item in lab.owned)
    return areas


def _check_areas(labs: list[Lab]) -> None:
    seen: dict[str, str] = {}
    for lab in labs:
        for area in _areas(lab):
            previous = seen.get(area)
            if previous is not None:
                raise CkaError(f"exam labs {previous} and {lab.id} overlap in {area}")
            seen[area] = lab.id


class ExamService:
    def __init__(self, progress: Progress | None = None, log: Callable[[str], None] = print) -> None:
        self.progress = progress or Progress()
        self.log = log

    def start(
        self,
        backend_name: str = "kind",
        *,
        cert: str = DEFAULT_CERT,
        duration_minutes: int = 120,
        pass_percent: int = 66,
        seed: int | None = None,
    ) -> ExamState:
        if load_session() is not None:
            raise CkaError("stop the active lab before starting an exam")
        if exam_active():
            raise CkaError("an exam is already in progress")
        if duration_minutes < 1 or duration_minutes > 480:
            raise CkaError("duration must be between 1 and 480 minutes")
        if pass_percent < 1 or pass_percent > 100:
            raise CkaError("pass threshold must be between 1 and 100 percent")

        backend = get_backend(backend_name)
        problems = backend.problems()
        if problems:
            raise CkaError("backend not ready:\n  " + "\n  ".join(problems))
        exam_seed = seed if seed is not None else new_seed()
        # A timed exam must be a single coherent environment. Namespace labs can
        # share the managed cluster safely; node/control-plane labs require a
        # separate VM/cluster per task and are therefore practice-only on kind.
        candidates = [
            source.meta()
            for source in catalog.discover().values()
            if backend_name in source.meta().backends and source.meta().isolation == "namespace"
        ]
        selected = _select(candidates, exam_seed, 8, cert)
        tasks: list[ExamTask] = []
        used: list[tuple[Cluster, Runner]] = []
        attempt_ids: list[int] = []
        cluster = backend.main()
        cluster.ensure()
        planned: list[tuple[int, Lab, int, Prepared]] = []
        for number, lab in enumerate(selected, 1):
            self.log(f"preparing task {number}/8: {getattr(lab, 'id')} on {cluster.name}")
            source = catalog.get(getattr(lab, "id"))
            task_seed = _stable_number(exam_seed, getattr(lab, "id")) % (2**31 - 1) or 1
            prepared = prepare(source, cluster, task_seed, self.log)
            planned.append((number, lab, task_seed, prepared))
        _check_areas([prepared.lab for _, _, _, prepared in planned])
        exam_id = self.progress.start_exam(
            backend=backend_name, seed=exam_seed, duration_minutes=duration_minutes, pass_percent=pass_percent
        )
        try:
            for number, lab, task_seed, prepared in planned:
                provision(prepared, self.log)
                used.append((cluster, prepared.runner))
                attempt = self.progress.start_attempt(
                    lab_id=prepared.lab.id,
                    mode="exam",
                    backend=backend_name,
                    seed=task_seed,
                    domain=prepared.lab.domain,
                    objectives=prepared.lab.objectives,
                    difficulty=prepared.lab.difficulty,
                    hints_total=len(prepared.lab.hints),
                    estimated_minutes=prepared.lab.estimated_minutes,
                    exam_id=exam_id,
                )
                attempt_ids.append(attempt)
                tasks.append(
                    ExamTask(
                        number=number,
                        lab_id=prepared.lab.id,
                        domain=prepared.lab.domain_in(cert) or prepared.lab.domain,
                        difficulty=prepared.lab.difficulty,
                        points=_points(prepared.lab.difficulty),
                        backend=backend_name,
                        cluster=cluster.name,
                        seed=task_seed,
                        values=prepared.values,
                        captured=prepared.runner.captured,
                        attempt_id=attempt,
                    )
                )
        except Exception:
            for attempt_id in attempt_ids:
                self.progress.finish_attempt(attempt_id, "cancelled")
            for cluster, runner in reversed(used):
                runner.cleanup()
            self.progress.finish_exam(
                exam_id,
                0,
                sum(task.points for task in tasks),
                {"aborted": True, "reason": "setup failed", "exam_id": exam_id},
            )
            clear_exam()
            raise
        state = ExamState(
            exam_id=exam_id,
            cert=cert,
            backend=backend_name,
            seed=exam_seed,
            started_at=time.time(),
            duration_minutes=duration_minutes,
            pass_percent=pass_percent,
            tasks=tasks,
            max_score=sum(task.points for task in tasks),
        )
        save_exam(state)
        return state

    def require(self) -> ExamState:
        exam = load_exam()
        if exam is None:
            raise CkaError("no active exam; start one with `cka exam start`")
        return exam

    def task(self, number: int | None = None) -> tuple[ExamState, ExamTask]:
        exam = self.require()
        if number is None:
            number = next((task.number for task in exam.tasks if task.status == "pending"), exam.tasks[0].number)
        task = next((task for task in exam.tasks if task.number == number), None)
        if task is None:
            raise CkaError(f"exam task {number} does not exist (1-{len(exam.tasks)})")
        return exam, task

    def skip(self, number: int | None = None) -> ExamState:
        exam, task = self.task(number)
        if task.status in ("passed", "failed"):
            raise CkaError(f"task {task.number} is already {task.status}")
        task.status = "skipped"
        self.progress.finish_attempt(task.attempt_id, "abandoned")
        save_exam(exam)
        return exam

    def grade(self) -> tuple[ExamState, dict[int, list[CheckResult]]]:
        exam = self.require()
        reports: dict[int, list[CheckResult]] = {}
        for task in exam.tasks:
            if task.status == "skipped":
                continue
            cluster = _cluster_for(exam, task)
            source = catalog.get(task.lab_id)
            prepared = prepare(source, cluster, task.seed, self.log, task.captured)
            results = evaluate_all(prepared.lab.checks, prepared.runner.context(), settle=True)
            reports[task.number] = results
            task.last_results = [
                {"id": result.id, "passed": result.passed, "detail": result.detail} for result in results
            ]
            passed = all(result.passed for result in results)
            task.status = "passed" if passed else "failed"
            self.progress.record_check(task.attempt_id, [result.id for result in results if not result.passed])
            self.progress.finish_attempt(task.attempt_id, "passed" if passed else "failed")
        save_exam(exam)
        return exam, reports

    def submit(self) -> tuple[ExamState, dict[int, list[CheckResult]]]:
        exam, reports = self.grade()
        score = sum(task.points for task in exam.tasks if task.status == "passed")
        max_score = sum(task.points for task in exam.tasks)
        exam.score = score
        exam.max_score = max_score
        exam.submitted_at = time.time()
        self.progress.finish_exam(
            exam.exam_id,
            score,
            max_score,
            {
                "exam_id": exam.exam_id,
                "cert": exam.cert,
                "seed": exam.seed,
                "score": score,
                "max_score": max_score,
                "percent": round(score / max_score * 100, 2) if max_score else 0,
                "pass_percent": exam.pass_percent,
                "passed": score / max_score * 100 >= exam.pass_percent if max_score else False,
                "tasks": [task.model_dump() for task in exam.tasks],
            },
        )
        save_exam(exam)
        self.cleanup(exam)
        clear_exam()
        return exam, reports

    def cleanup(self, exam: ExamState | None = None) -> None:
        exam = exam or self.require()
        seen: set[str] = set()
        for task in exam.tasks:
            if task.cluster in seen:
                continue
            seen.add(task.cluster)
            cluster = _cluster_for(exam, task)
            # A cluster can contain namespace tasks from several labs; clean each task
            # on its own, but never call kind delete here.
            for owned_task in [candidate for candidate in exam.tasks if candidate.cluster == task.cluster]:
                prepared = prepare(catalog.get(owned_task.lab_id), cluster, owned_task.seed, self.log, owned_task.captured)
                prepared.runner.cleanup()


def _cluster_for(exam: ExamState, task: ExamTask) -> Cluster:
    backend = get_backend(exam.backend)
    if task.cluster == backend.main().name:
        return backend.main()
    for index in range(1, backend.max_extra_clusters + 1):
        if backend.extra(index).name == task.cluster:
            return backend.extra(index)
    raise CkaError(f"exam task references unknown managed cluster {task.cluster}")
