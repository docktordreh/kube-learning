"""Executes lab setup and cleanup against one managed cluster.

Ownership rules (see docs/safety.org):
- namespaces listed in lab.namespaces are created with the label cka-labs.io/lab=<id>;
  cleanup deletes namespaces by that label only;
- other resources are deleted only when listed explicitly in lab.owned (kind/name).
"""

import shutil
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

from cka_labs import paths, proc
from cka_labs.backends.base import LAB_LABEL, Cluster
from cka_labs.engine import components
from cka_labs.engine.catalog import LabSource, workdir
from cka_labs.engine.evaluator import CheckResult, GradeContext, evaluate_all, wait_for
from cka_labs.errors import CkaError
from cka_labs.kube import Kube
from cka_labs.models import ApplyStep, CaptureStep, KubectlStep, Lab, NodeStep, ScriptStep, Step, WaitStep

Log = Callable[[str], None]


class SetupError(CkaError):
    """The scenario did not reach its intended starting state."""


@dataclass
class Runner:
    cluster: Cluster
    source: LabSource
    lab: Lab
    values: Mapping[str, str]
    log: Log = lambda _: None
    captured: dict[str, str] = field(default_factory=dict)

    @property
    def admin(self) -> Kube:
        return self.cluster.admin()

    def context(self) -> GradeContext:
        return GradeContext(self.cluster, self.cluster.grader(), self.captured)

    # --- setup ----------------------------------------------------------------------------

    def setup(self) -> None:
        self.admin.verify_marker()
        components.ensure(self.cluster, self.lab.requires, self.log)
        paths.ensure(workdir(self.lab.id))
        for namespace in self.lab.namespaces:
            manifest = (
                f"apiVersion: v1\nkind: Namespace\nmetadata:\n  name: {namespace}\n"
                f"  labels:\n    {LAB_LABEL}: {self.lab.id}\n"
            )
            self.admin.must(["apply", "-f", "-"], stdin=manifest)
        for step in self.lab.setup:
            self.run_step(step, phase="setup")

    def verify_initial_state(self) -> list[CheckResult]:
        """Goals must fail and guards must pass before the student starts."""
        results = evaluate_all(self.lab.checks, self.context(), settle=False)
        wrong = [r for r in results if r.passed == (r.role == "goal")]
        if wrong:
            lines = "\n".join(f"  - [{r.role}] {r.id}: {r.detail}" for r in wrong)
            raise SetupError(f"{self.lab.id}: scenario is not in its intended starting state:\n{lines}")
        return results

    # --- cleanup --------------------------------------------------------------------------

    def cleanup(self) -> None:
        if not self.admin.reachable():
            self.log("API server unreachable; running node-level cleanup steps only")
        else:
            self.admin.verify_marker()
        for step in self.lab.cleanup:
            try:
                self.run_step(step, phase="cleanup")
            except CkaError as exc:
                self.log(f"cleanup step failed (continuing): {exc}")
        # Namespaces first: claims inside them must go before their PersistentVolumes can.
        if self.lab.namespaces:
            self.admin.kubectl(
                ["delete", "namespace", "-l", f"{LAB_LABEL}={self.lab.id}", "--wait=true", "--timeout=180s"],
                timeout=200,
            )
        for item in self.lab.owned:
            self.admin.kubectl(["delete", item, "--ignore-not-found", "--wait=true", "--timeout=120s"], timeout=150)
        # Only the lab's own work directory (paths.home()/work/<lab-id>), never a user path.
        shutil.rmtree(workdir(self.lab.id), ignore_errors=True)

    # --- steps ----------------------------------------------------------------------------

    def run_step(self, step: Step, *, phase: str) -> None:
        match step:
            case ApplyStep():
                manifest = self.source.read(step.apply, self.values)
                self.admin.must(["apply", "-f", "-"], stdin=manifest, timeout=120)
            case KubectlStep():
                result = self.admin.kubectl(step.kubectl, timeout=180)
                if not result.ok and not step.ignore_errors:
                    raise SetupError(f"{phase}: kubectl {' '.join(step.kubectl)} failed: {result.output()}")
            case WaitStep():
                result = wait_for(step.wait, self.context(), step.timeout)
                if not result.passed:
                    raise SetupError(f"{phase}: timed out after {step.timeout}s waiting for: {result.detail}")
            case NodeStep():
                result = self.cluster.node_exec(step.node, step.run, timeout=300)
                if not result.ok and not step.ignore_errors:
                    raise SetupError(f"{phase}: script on {step.node} failed ({result.returncode}): {result.output()}")
            case ScriptStep():
                result = proc.run(["bash", "-c", step.script], env=self.script_env(), timeout=300)
                if not result.ok and not step.ignore_errors:
                    raise SetupError(f"{phase}: script failed ({result.returncode}): {result.output()}")
            case CaptureStep():
                ns = ["-n", step.namespace] if step.namespace else []
                value = self.admin.must(["get", step.resource, *ns, "-o", f"jsonpath={step.jsonpath}"]).strip()
                self.captured[step.capture] = value

    def script_env(self) -> dict[str, str]:
        """Environment for host scripts and reference solutions: admin kubeconfig, cka on PATH."""
        env = proc.tool_env(self.admin.env())
        env["PATH"] = f"{Path(sys.executable).parent}:{env['PATH']}"
        env["CKA_CLUSTER"] = self.cluster.name
        env["CKA_BACKEND"] = self.cluster.backend_name
        env["CKA_WORKDIR"] = str(workdir(self.lab.id))
        return env
