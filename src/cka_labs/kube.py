"""kubectl bound to one explicit kubeconfig. The user's ~/.kube/config is never consulted."""

import json
from collections.abc import Sequence
from pathlib import Path

from cka_labs import proc
from cka_labs.errors import CkaError, SafetyError
from cka_labs.proc import Result

MARKER_NAMESPACE = "kube-system"
MARKER_NAME = "cka-labs-cluster"


class Kube:
    def __init__(self, kubeconfig: Path, cluster_id: str) -> None:
        self.kubeconfig = kubeconfig
        self.cluster_id = cluster_id

    def env(self) -> dict[str, str]:
        # KUBECONFIG is set as well so that child processes (solution scripts) inherit it.
        return {"KUBECONFIG": str(self.kubeconfig)}

    def kubectl(self, args: Sequence[str], *, stdin: str | None = None, timeout: float = 60) -> Result:
        if not self.kubeconfig.is_file():
            raise CkaError(f"kubeconfig {self.kubeconfig} missing; run `cka cluster up`")
        return proc.run(
            ["kubectl", f"--kubeconfig={self.kubeconfig}", *args],
            env=self.env(),
            stdin=stdin,
            timeout=timeout,
        )

    def must(self, args: Sequence[str], *, stdin: str | None = None, timeout: float = 60) -> str:
        result = self.kubectl(args, stdin=stdin, timeout=timeout)
        if not result.ok:
            raise CkaError(f"kubectl {' '.join(args)} failed:\n{result.output()}")
        return result.stdout

    def get_json(self, args: Sequence[str], timeout: float = 30) -> dict[str, object] | None:
        result = self.kubectl([*args, "-o", "json"], timeout=timeout)
        if not result.ok:
            return None
        loaded: object = json.loads(result.stdout)
        return loaded if isinstance(loaded, dict) else None

    def reachable(self) -> bool:
        return self.kubectl(["get", "--raw", "/readyz"], timeout=10).ok

    def verify_marker(self) -> None:
        """Refuse to touch a cluster that does not carry this cka cluster's marker."""
        result = self.kubectl(
            ["get", "configmap", MARKER_NAME, "-n", MARKER_NAMESPACE, "-o", "jsonpath={.data.cluster-id}"],
            timeout=15,
        )
        if not result.ok:
            raise SafetyError(
                f"cannot read marker {MARKER_NAMESPACE}/{MARKER_NAME} via {self.kubeconfig}: "
                f"{result.output()}\nRefusing to modify a cluster that cka cannot identify."
            )
        if result.stdout.strip() != self.cluster_id:
            raise SafetyError(
                f"cluster marker {result.stdout.strip()!r} != expected {self.cluster_id!r}; refusing to continue"
            )
