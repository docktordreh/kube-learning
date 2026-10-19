"""Lab conformance cycle against a real cluster.

For one lab and seed:
 1. start: setup + fault injection; goals must fail and guards pass (else SetupError)
 2. the reference solution (solution.sh) runs
 3. grading passes (all goals and guards)
 4. reset restores the broken starting state (goals fail again)
 5. stop removes the lab's owned resources and nothing else (a sentinel survives)
Progress is recorded in a throwaway database, never in the user's history.
"""

import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from cka_labs.backends import get_backend
from cka_labs.backends.base import LAB_LABEL
from cka_labs.engine import catalog
from cka_labs.engine.evaluator import evaluate_all
from cka_labs.engine.lifecycle import LabService, exam_active, find_cluster, load_session, prepare
from cka_labs.engine.progress import Progress
from cka_labs.errors import CkaError

SENTINEL_NS = "cka-sentinel"
# An unrelated namespace + object that no lab owns; cleanup must leave it alone.
SENTINEL = f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {SENTINEL_NS}
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: keep-me
  namespace: {SENTINEL_NS}
data:
  purpose: cleanup-scope-sentinel
"""


@dataclass
class Report:
    lab_id: str
    ok: bool = False
    seconds: float = 0.0
    lines: list[str] = field(default_factory=list)


def verify_lab(lab_id: str, backend: str, seed: int, log: Callable[[str], None]) -> Report:
    if load_session() is not None or exam_active():
        raise CkaError("stop the active lab/exam before running conformance verification")
    report = Report(lab_id)
    started = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        service = LabService(progress=Progress(Path(tmp) / "verify.db"), log=log)
        try:
            _cycle(service, lab_id, backend, seed, report)
            report.ok = True
        except CkaError as exc:
            report.lines.append(f"✘ {exc}")
            if load_session() is not None:
                try:
                    service.stop()
                except CkaError as cleanup_exc:
                    report.lines.append(f"✘ cleanup after failure: {cleanup_exc}")
    report.seconds = time.monotonic() - started
    return report


def _cycle(service: LabService, lab_id: str, backend: str, seed: int, report: Report) -> None:
    cluster = get_backend(backend).main()
    cluster.ensure()
    admin = cluster.admin()
    admin.verify_marker()
    admin.must(["apply", "-f", "-"], stdin=SENTINEL)

    session, lab = service.start(lab_id, backend, seed)
    report.lines.append("✔ setup reached the intended broken state (goals fail, guards pass)")

    service.solve_reference()
    report.lines.append("✔ reference solution ran")

    _, results = service.check()
    failing = [r for r in results if not r.passed]
    if failing:
        raise CkaError("reference solution did not pass grading: " + "; ".join(f"{r.id}: {r.detail}" for r in failing))
    report.lines.append(f"✔ grading passed ({len(results)} checks)")

    service.reset()
    session = service.require_session()
    prepared = prepare(catalog.get(lab_id), find_cluster(session.backend, session.cluster), session.seed, lambda _: None, session.captured)
    after_reset = evaluate_all(lab.checks, prepared.runner.context(), settle=False)
    if any(r.passed for r in after_reset if r.role == "goal"):
        raise CkaError("reset did not restore the broken state")
    report.lines.append("✔ reset restored the broken state")

    service.stop()
    leftovers = admin.kubectl(["get", "namespace", "-l", f"{LAB_LABEL}={lab_id}", "-o", "name"]).stdout.strip()
    if leftovers:
        raise CkaError(f"cleanup left namespaces behind: {leftovers}")
    for item in lab.owned:
        if admin.kubectl(["get", item, "--ignore-not-found", "-o", "name"]).stdout.strip():
            raise CkaError(f"cleanup left {item} behind")
    if not admin.kubectl(["get", "configmap", "keep-me", "-n", SENTINEL_NS]).ok:
        raise CkaError("cleanup deleted an unrelated resource (sentinel configmap)")
    nodes = admin.kubectl(["get", "nodes", "--no-headers"]).stdout
    if " NotReady" in nodes:
        raise CkaError(f"cleanup left a node NotReady:\n{nodes}")
    report.lines.append("✔ cleanup removed only lab-owned resources; nodes Ready")
