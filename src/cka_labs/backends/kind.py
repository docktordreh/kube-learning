"""kind backend: Kubernetes-in-Docker clusters.

kind nodes are containers running systemd, containerd and a kubeadm-built kubelet with
static control-plane Pods in /etc/kubernetes/manifests. Kubelet, static Pod and component
configuration faults are therefore genuine. Not available here: package-based kubeadm
upgrades, kernel modules/sysctls (shared host kernel), and VM-level disk/network faults;
those labs require the kubeadm backend.
"""

import json
import os
import shutil

from cka_labs import paths, proc
from cka_labs.backends.base import Backend, Cluster
from cka_labs.config import toolchain
from cka_labs.errors import CkaError, SafetyError
from cka_labs.proc import Result

MAIN_CLUSTER = "cka-labs"
KIND_LABEL = "io.x-k8s.kind.cluster"

CLUSTER_CONFIG = """\
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
  - role: worker
  - role: worker
"""


class KindCluster(Cluster):
    backend_name = "kind"

    def exists(self) -> bool:
        result = proc.run(["kind", "get", "clusters"], timeout=30)
        return result.ok and self.name in result.stdout.split()

    def create(self) -> None:
        paths.ensure(self.state_dir)
        if self.exists():
            self._require_created_by_cka()
            # Re-export credentials into the cka kubeconfig; never touches ~/.kube/config.
            proc.run(
                ["kind", "export", "kubeconfig", f"--name={self.name}", f"--kubeconfig={self.kubeconfig}"],
                timeout=60,
                check=True,
            )
            self.kubeconfig.chmod(0o600)
            self.bootstrap()
            return
        config = self.state_dir / "kind-config.yaml"
        config.write_text(CLUSTER_CONFIG)
        paths.ensure(self.kubeconfig.parent)
        proc.run(
            [
                "kind",
                "create",
                "cluster",
                f"--name={self.name}",
                f"--image={toolchain().kind.node_image}",
                f"--config={config}",
                f"--kubeconfig={self.kubeconfig}",
                "--wait=180s",
            ],
            timeout=600,
            check=True,
        )
        self.kubeconfig.chmod(0o600)
        (self.state_dir / "created-by-cka").write_text(self.name)
        (self.state_dir / "cluster.json").unlink(missing_ok=True)
        self.bootstrap()
        self.load_images(toolchain().images)

    def delete(self) -> None:
        if self.exists():
            self._require_created_by_cka()
            # --kubeconfig: kind otherwise prunes contexts from $KUBECONFIG / ~/.kube/config.
            proc.run(
                ["kind", "delete", "cluster", f"--name={self.name}", f"--kubeconfig={self.kubeconfig}"],
                timeout=300,
                check=True,
            )
        for path in (
            self.kubeconfig,
            self.grader_kubeconfig,
            self.state_dir / "cluster.json",
            self.state_dir / "created-by-cka",
        ):
            path.unlink(missing_ok=True)

    def _require_created_by_cka(self) -> None:
        if not (self.state_dir / "created-by-cka").is_file():
            raise SafetyError(
                f"a kind cluster named {self.name!r} exists but was not created by cka "
                f"(no {self.state_dir / 'created-by-cka'}). cka will not adopt or delete it. "
                f"Remove it yourself or set CKA_KIND_CLUSTER to use another name."
            )

    def nodes(self) -> dict[str, str]:
        return {
            "controlplane": f"{self.name}-control-plane",
            "worker1": f"{self.name}-worker",
            "worker2": f"{self.name}-worker2",
        }

    def node_exec(self, node: str, script: str, timeout: float = 120) -> Result:
        container = self.resolve_node(node)
        self._require_owned_container(container)
        return proc.run(["docker", "exec", "-i", container, "bash", "-s"], stdin=script, timeout=timeout)

    def node_shell(self, node: str) -> int:
        container = self.resolve_node(node)
        self._require_owned_container(container)
        return proc.interactive(["docker", "exec", "-it", "-w", "/root", container, "bash", "-l"])

    def load_images(self, images: list[str]) -> None:
        for image in images:
            if not proc.run(["docker", "image", "inspect", image], timeout=30).ok:
                proc.run(["docker", "pull", image], timeout=600, check=True)
        if images:
            proc.run(["kind", "load", "docker-image", f"--name={self.name}", *images], timeout=900, check=True)

    def _require_owned_container(self, container: str) -> None:
        """Only ever exec into containers that kind labelled as part of this cluster."""
        result = proc.run(["docker", "inspect", "--format", "{{json .Config.Labels}}", container], timeout=30)
        if not result.ok:
            raise CkaError(f"node container {container} not found; is the cluster running? (`cka cluster up`)")
        labels: object = json.loads(result.stdout)
        if not isinstance(labels, dict) or labels.get(KIND_LABEL) != self.name:
            raise SafetyError(f"container {container} is not a node of kind cluster {self.name}; refusing")


class KindBackend(Backend):
    name = "kind"

    def __init__(self) -> None:
        self.cluster_name = os.environ.get("CKA_KIND_CLUSTER", MAIN_CLUSTER)

    def main(self) -> KindCluster:
        return KindCluster(self.cluster_name)

    def extra(self, index: int) -> KindCluster:
        return KindCluster(f"{self.cluster_name}-x{index}")

    @property
    def max_extra_clusters(self) -> int:
        return 3

    def problems(self) -> list[str]:
        found: list[str] = []
        for tool in ("docker", "kind", "kubectl"):
            if shutil.which(tool, path=proc.tool_env()["PATH"]) is None:
                found.append(f"{tool} not found (run `cka setup`)")
        if not found and not proc.run(["docker", "info", "--format", "{{.ServerVersion}}"], timeout=30).ok:
            found.append("cannot talk to the Docker daemon (is it running, are you in the docker group?)")
        return found
