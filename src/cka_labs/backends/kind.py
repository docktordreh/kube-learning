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
import tempfile
from pathlib import Path

from cka_labs import paths, proc, tools
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

    def ensure(self) -> None:
        super().ensure()
        self.install_node_tools()

    def install_node_tools(self) -> None:
        """kind node images ship no editor. Copy a static busybox (vi, less) from the cached
        busybox image into each node, as the exam's nodes have an editor."""
        missing = [n for n in self.nodes().values() if not self.node_exec(n, "test -x /usr/local/bin/vi", 30).ok]
        if not missing:
            return
        image = next(i for i in toolchain().images if "/busybox:" in i)
        created = proc.run(["docker", "create", image, "true"], timeout=60, check=True).stdout.strip()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                binary = f"{tmp}/busybox"
                proc.run(["docker", "cp", f"{created}:/bin/busybox", binary], timeout=60, check=True)
                for node in missing:
                    self._require_owned_container(node)
                    proc.run(["docker", "cp", binary, f"{node}:/usr/local/bin/busybox"], timeout=60, check=True)
                    self.node_exec(node, "cd /usr/local/bin && for t in vi less; do ln -sf busybox $t; done", 30)
        finally:
            proc.run(["docker", "rm", created], timeout=60)

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

    def verify_ownership(self) -> None:
        self._require_created_by_cka()
        for node in self.nodes().values():
            self._require_owned_container(node)

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
            _, machine = tools.platform_pair()
            with tempfile.TemporaryDirectory(prefix="cka-images-") as directory:
                archive = os.path.join(directory, "images.tar")
                saved = proc.run(
                    [
                        "docker", "image", "save", f"--platform=linux/{machine}",
                        f"--output={archive}", *images,
                    ],
                    timeout=900,
                )
                if not saved.ok:
                    # Older Docker releases do not understand --platform for image save.
                    proc.run(
                        ["docker", "image", "save", f"--output={archive}", *images],
                        timeout=900,
                        check=True,
                    )
                proc.run(
                    ["kind", "load", "image-archive", archive, f"--name={self.name}"],
                    timeout=900,
                    check=True,
                )

    def load_archive(self, archive: Path) -> None:
        """Import an image archive (docker save, podman save, OCI) into every node."""
        proc.run(["kind", "load", "image-archive", str(archive), f"--name={self.name}"], timeout=900, check=True)

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
