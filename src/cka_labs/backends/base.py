"""Backend abstraction.

A Backend owns one or more disposable Clusters. A Cluster exposes:
- an admin kubeconfig (student and setup steps) and a read-only grader kubeconfig,
- node access (shell scripts on nodes) for node-level and control-plane exercises,
- a marker ConfigMap that every mutating code path verifies first.
"""

import json
import os
import time
import uuid
from abc import ABC, abstractmethod
from pathlib import Path

import yaml

from cka_labs import paths
from cka_labs.errors import CkaError
from cka_labs.kube import MARKER_NAME, MARKER_NAMESPACE, Kube
from cka_labs.proc import Result

GRADER_NAMESPACE = "cka-system"
GRADER_SA = "cka-grader"
LAB_LABEL = "cka-labs.io/lab"

GRADER_RBAC = f"""
apiVersion: v1
kind: Namespace
metadata:
  name: {GRADER_NAMESPACE}
  labels:
    cka-labs.io/system: "true"
---
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {GRADER_SA}
  namespace: {GRADER_NAMESPACE}
---
# Read everything, exec into pods, and ask SubjectAccessReviews. Nothing else.
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: cka-grader
  labels:
    cka-labs.io/system: "true"
rules:
  - apiGroups: ["*"]
    resources: ["*"]
    verbs: ["get", "list", "watch"]
  - nonResourceURLs: ["*"]
    verbs: ["get"]
  - apiGroups: [""]
    resources: ["pods/exec"]
    verbs: ["create", "get"]
  - apiGroups: ["authorization.k8s.io"]
    resources: ["subjectaccessreviews"]
    verbs: ["create"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: cka-grader
  labels:
    cka-labs.io/system: "true"
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: cka-grader
subjects:
  - kind: ServiceAccount
    name: {GRADER_SA}
    namespace: {GRADER_NAMESPACE}
"""


class Cluster(ABC):
    backend_name: str

    def __init__(self, name: str) -> None:
        self.name = name

    # --- identity and credentials ---------------------------------------------------------

    @property
    def state_dir(self) -> Path:
        return paths.backends_dir() / self.backend_name / self.name

    @property
    def kubeconfig(self) -> Path:
        return paths.kubeconfig_dir() / f"{self.backend_name}-{self.name}.yaml"

    @property
    def grader_kubeconfig(self) -> Path:
        return paths.kubeconfig_dir() / f"{self.backend_name}-{self.name}-grader.yaml"

    @property
    def cluster_id(self) -> str:
        marker = self.state_dir / "cluster.json"
        if not marker.is_file():
            raise CkaError(f"cluster {self.name} is not initialised; run `cka cluster up`")
        data: object = json.loads(marker.read_text())
        if not isinstance(data, dict) or not isinstance(data.get("id"), str):
            raise CkaError(f"corrupt {marker}")
        return data["id"]

    def admin(self) -> Kube:
        return Kube(self.kubeconfig, self.cluster_id)

    def grader(self) -> Kube:
        return Kube(self.grader_kubeconfig, self.cluster_id)

    def verify_ownership(self) -> None:
        """Verify local ownership when the API server cannot be queried."""
        if not (self.state_dir / "created-by-cka").is_file():
            raise SafetyError(f"cluster {self.name!r} has no cka ownership marker; refusing node mutation")

    # --- lifecycle ------------------------------------------------------------------------

    @abstractmethod
    def exists(self) -> bool: ...

    @abstractmethod
    def create(self) -> None:
        """Provision the cluster and write self.kubeconfig. Must be idempotent."""

    @abstractmethod
    def delete(self) -> None:
        """Remove only this cluster's own resources."""

    def ensure(self) -> None:
        if not self.exists() or not self.kubeconfig.is_file():
            self.create()
        if not (self.state_dir / "cluster.json").is_file() or not self.grader_kubeconfig.is_file():
            self.bootstrap()
        self.admin().verify_marker()

    def bootstrap(self) -> None:
        """Install the identity marker and the read-only grader identity."""
        admin = Kube(self.kubeconfig, cluster_id="")
        self._wait_api(admin)
        existing = admin.kubectl(
            ["get", "configmap", MARKER_NAME, "-n", MARKER_NAMESPACE, "-o", "jsonpath={.data.cluster-id}"]
        )
        if existing.ok and existing.stdout.strip():
            cluster_id = existing.stdout.strip()
        else:
            cluster_id = f"{self.backend_name}-{self.name}-{uuid.uuid4()}"
            admin.must(
                [
                    "create",
                    "configmap",
                    MARKER_NAME,
                    "-n",
                    MARKER_NAMESPACE,
                    f"--from-literal=cluster-id={cluster_id}",
                    f"--from-literal=created={int(time.time())}",
                ]
            )
        paths.ensure(self.state_dir)
        (self.state_dir / "cluster.json").write_text(json.dumps({"id": cluster_id, "name": self.name}))
        admin.must(["apply", "-f", "-"], stdin=GRADER_RBAC)
        token = admin.must(
            ["create", "token", GRADER_SA, "-n", GRADER_NAMESPACE, "--duration=8760h"]
        ).strip()
        self._write_grader_kubeconfig(token)

    def _write_grader_kubeconfig(self, token: str) -> None:
        loaded: object = yaml.safe_load(self.kubeconfig.read_text())
        if not isinstance(loaded, dict):
            raise CkaError(f"cannot parse {self.kubeconfig}")
        clusters = loaded.get("clusters")
        if not isinstance(clusters, list) or not clusters:
            raise CkaError(f"no cluster entry in {self.kubeconfig}")
        cluster_entry = clusters[0]
        config = {
            "apiVersion": "v1",
            "kind": "Config",
            "clusters": [cluster_entry],
            "users": [{"name": GRADER_SA, "user": {"token": token}}],
            "contexts": [
                {
                    "name": f"{self.name}-grader",
                    "context": {"cluster": cluster_entry["name"], "user": GRADER_SA},
                }
            ],
            "current-context": f"{self.name}-grader",
        }
        write_private(self.grader_kubeconfig, yaml.safe_dump(config))

    @staticmethod
    def _wait_api(kube: Kube, timeout: float = 180) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if kube.reachable():
                return
            time.sleep(2)
        raise CkaError(f"API server behind {kube.kubeconfig} not ready after {timeout}s")

    # --- nodes ----------------------------------------------------------------------------

    @abstractmethod
    def nodes(self) -> dict[str, str]:
        """Logical node name (controlplane, worker1, worker2) -> Kubernetes node name."""

    @abstractmethod
    def node_exec(self, node: str, script: str, timeout: float = 120) -> Result:
        """Run a bash script as root on a node (Kubernetes node name)."""

    @abstractmethod
    def node_shell(self, node: str) -> int:
        """Interactive root shell on a node."""

    def resolve_node(self, node: str) -> str:
        mapping = self.nodes()
        if node in mapping:
            return mapping[node]
        if node in mapping.values():
            return node
        raise CkaError(f"unknown node {node!r} in cluster {self.name}; nodes: {', '.join(mapping.values())}")

    def load_images(self, images: list[str]) -> None:
        """Make lab images available on every node without registry access."""


class Backend(ABC):
    name: str

    @abstractmethod
    def main(self) -> Cluster:
        """The shared practice cluster."""

    @abstractmethod
    def extra(self, index: int) -> Cluster:
        """An additional isolated cluster (exam tasks with isolation=cluster)."""

    @property
    def max_extra_clusters(self) -> int:
        return 0

    @property
    def main_is_dedicated(self) -> bool:
        """Whether the backend's main cluster is isolated for one lab."""
        return False

    @abstractmethod
    def problems(self) -> list[str]:
        """Missing prerequisites; empty when the backend is usable."""

    def owns_node(self, node: str) -> Cluster | None:
        """The managed cluster that owns a Kubernetes node name, if any."""
        candidates = [self.main(), *(self.extra(i) for i in range(1, self.max_extra_clusters + 1))]
        for cluster in candidates:
            if cluster.exists() and node in cluster.nodes().values():
                return cluster
        return None


def write_private(path: Path, content: str) -> None:
    paths.ensure(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as handle:
        handle.write(content)
