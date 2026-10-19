"""kubeadm backend using a cka-owned Vagrant/libvirt VM project.

The repository already contains a useful three-VM practice lab in ``cka/``. This
backend copies its inputs into ``$CKA_LABS_HOME/backends/kubeadm/project`` and
rewrites the network to 192.168.251.0/24. Consequently the backend never shares
Vagrant state, VM names, disks, or IPs with that hand-managed lab.
"""

import os
import shlex
import shutil
import time
from pathlib import Path

from cka_labs import paths, proc
from cka_labs.backends.base import Backend, Cluster, write_private
from cka_labs.config import toolchain
from cka_labs.errors import CkaError, SafetyError
from cka_labs.proc import Result


class KubeadmCluster(Cluster):
    backend_name = "kubeadm"

    def __init__(self, name: str, project: Path) -> None:
        super().__init__(name)
        self.project = project

    @property
    def state_dir(self) -> Path:
        return paths.backends_dir() / self.backend_name / self.name

    def _vagrant_env(self) -> dict[str, str]:
        tc = toolchain().kubeadm
        return {
            "VAGRANT_CWD": str(self.project),
            "VAGRANT_DEFAULT_PROVIDER": "libvirt",
            "VAGRANT_DOTFILE_PATH": str(self.project / ".vagrant"),
            "KUBERNETES_MINOR_VERSION": tc.kubernetes_minor,
            "CRICTL_VERSION": tc.crictl_version,
        }

    def exists(self) -> bool:
        if not self.project.is_dir() or not shutil.which("vagrant"):
            return False
        result = proc.run(["vagrant", "status", "--machine-readable"], env=self._vagrant_env(), timeout=60)
        return result.ok and any(
            ",state," in line and state not in {"not-created", ""}
            for line in result.stdout.splitlines()
            for state in [line.rsplit(",", 1)[-1]]
        )

    def create(self) -> None:
        self._require_owned_project()
        paths.ensure(self.state_dir)
        proc.run(["vagrant", "up"], env=self._vagrant_env(), timeout=1800, check=True)
        self._prepare_nodes()
        admin_conf = self.project / "admin.conf"
        if not admin_conf.is_file():
            self._init_control_plane()
            self._join_workers()
        self._install_cni(admin_conf)
        write_private(self.kubeconfig, admin_conf.read_text())
        self.kubeconfig.chmod(0o600)

    def _prepare_nodes(self) -> None:
        """Prepare only the disposable guest kernels for kubeadm's baseline checks."""
        script = """
set -eu
swapoff --all
modprobe overlay
modprobe br_netfilter
install -d -m 0755 /etc/modules-load.d /etc/sysctl.d
printf '%s\\n' overlay br_netfilter > /etc/modules-load.d/cka-kubernetes.conf
cat > /etc/sysctl.d/99-cka-kubernetes.conf <<'EOF'
net.ipv4.ip_forward = 1
net.bridge.bridge-nf-call-iptables = 1
net.bridge.bridge-nf-call-ip6tables = 1
EOF
sysctl --system >/dev/null
systemctl enable --now containerd
"""
        for node in self.nodes():
            result = self.node_exec(node, script, timeout=180)
            if not result.ok:
                raise CkaError(f"failed to prepare kubeadm node {node}: {result.output()}")

    def delete(self) -> None:
        self._require_owned_project()
        if not (self.state_dir / "created-by-cka").is_file():
            raise SafetyError("refusing to destroy kubeadm VMs without cka ownership marker")
        if self.exists():
            proc.run(["vagrant", "destroy", "--force"], env=self._vagrant_env(), timeout=1800, check=True)
        for path in (self.kubeconfig, self.grader_kubeconfig, self.state_dir / "cluster.json"):
            path.unlink(missing_ok=True)

    def nodes(self) -> dict[str, str]:
        return {
            "controlplane": "control-plane",
            "worker1": "worker-1",
            "worker2": "worker-2",
        }

    def node_exec(self, node: str, script: str, timeout: float = 120) -> Result:
        machine = self._machine(node)
        # vagrant passes the command through SSH; quote the script as one argument.
        command = f"sudo bash -c {shlex.quote(script)}"
        return proc.run(["vagrant", "ssh", machine, "-c", command], env=self._vagrant_env(), timeout=timeout)

    def node_shell(self, node: str) -> int:
        return proc.interactive(
            ["vagrant", "ssh", self._machine(node), "-c", "sudo -i"], env=self._vagrant_env()
        )

    def _machine(self, node: str) -> str:
        mapping = self.nodes()
        if node in mapping:
            return mapping[node]
        if node in mapping.values():
            return node
        raise CkaError(f"unknown kubeadm node {node!r}")

    def _init_control_plane(self) -> None:
        result = self.node_exec("controlplane", "test -f /etc/kubernetes/admin.conf", timeout=60)
        if result.ok:
            admin = self.node_exec("controlplane", "cat /etc/kubernetes/admin.conf", timeout=60)
            if not admin.ok:
                raise CkaError(f"could not read existing kubeadm admin.conf: {admin.output()}")
            write_private(self.project / "admin.conf", admin.stdout)
            return
        init = self.node_exec(
            "controlplane",
            "kubeadm init --config /root/kubeadm-config.yaml --upload-certs",
            timeout=900,
        )
        if not init.ok:
            raise CkaError(f"kubeadm init failed: {init.output()}")
        admin = self.node_exec("controlplane", "cat /etc/kubernetes/admin.conf", timeout=60)
        if not admin.ok:
            raise CkaError(f"could not read kubeadm admin.conf: {admin.output()}")
        write_private(self.project / "admin.conf", admin.stdout)

    def _join_workers(self) -> None:
        join = self.node_exec(
            "controlplane", "kubeadm token create --print-join-command", timeout=120
        )
        if not join.ok:
            raise CkaError(f"could not create kubeadm join command: {join.output()}")
        command = join.stdout.strip().splitlines()[-1]
        if not command.startswith("kubeadm join "):
            raise CkaError(f"unexpected kubeadm join output: {join.stdout}")
        for worker in ("worker1", "worker2"):
            joined = self.node_exec(worker, "test -f /etc/kubernetes/kubelet.conf", timeout=30)
            if not joined.ok:
                result = self.node_exec(worker, f"{command} --cri-socket unix:///run/containerd/containerd.sock", timeout=900)
                if not result.ok:
                    raise CkaError(f"{worker} failed to join: {result.output()}")

    def _install_cni(self, admin_conf: Path) -> None:
        if proc.run(
            ["kubectl", f"--kubeconfig={admin_conf}", "get", "daemonset", "calico-node", "-n", "kube-system"],
            timeout=30,
        ).ok:
            self._wait_cni(admin_conf)
            return
        url = (
            f"https://raw.githubusercontent.com/projectcalico/calico/"
            f"{toolchain().kubeadm.calico_version}/manifests/calico.yaml"
        )
        result = proc.run(["kubectl", f"--kubeconfig={admin_conf}", "apply", "-f", url], timeout=600)
        if not result.ok:
            raise CkaError(
                "Calico was not cached and could not be downloaded. Download the pinned manifest "
                f"before an offline run: {url}\n{result.output()}"
            )
        # The pinned manifest uses Calico's default pool; align it with kubeadm's podSubnet.
        proc.run(
            [
                "kubectl",
                f"--kubeconfig={admin_conf}",
                "-n",
                "kube-system",
                "set",
                "env",
                "daemonset/calico-node",
                f"CALICO_IPV4POOL_CIDR={toolchain().kubeadm.pod_subnet}",
            ],
            timeout=120,
            check=True,
        )
        self._wait_cni(admin_conf)

    @staticmethod
    def _wait_cni(admin_conf: Path) -> None:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            daemonset = proc.run(
                [
                    "kubectl",
                    f"--kubeconfig={admin_conf}",
                    "-n",
                    "kube-system",
                    "get",
                    "daemonset",
                    "calico-node",
                    "-o",
                    "jsonpath={.status.desiredNumberScheduled} {.status.numberReady} {.status.numberAvailable}",
                ],
                timeout=30,
            )
            deployment = proc.run(
                [
                    "kubectl",
                    f"--kubeconfig={admin_conf}",
                    "-n",
                    "kube-system",
                    "get",
                    "deployment",
                    "calico-kube-controllers",
                    "-o",
                    "jsonpath={.status.availableReplicas}",
                ],
                timeout=30,
            )
            status = daemonset.stdout.split() if daemonset.ok else []
            desired, ready, available = (status + ["0", "0", "0"])[:3]
            if daemonset.ok and deployment.ok and desired != "0" and desired == ready == available and deployment.stdout.strip() == "1":
                return
            time.sleep(5)
        raise CkaError("Calico did not become ready on every node within 300s")

    def _require_owned_project(self) -> None:
        if not self.project.is_dir():
            raise CkaError(f"kubeadm project missing: {self.project}; run `cka setup --kubeadm`")
        marker = self.project / ".cka-project"
        if not marker.is_file() or marker.read_text().strip() != self.name:
            raise SafetyError(f"{self.project} is not a cka-owned kubeadm project")

class KubeadmBackend(Backend):
    name = "kubeadm"

    def __init__(self) -> None:
        self.source = Path(os.environ.get("CKA_KUBEADM_SOURCE", paths.PACKAGE_DIR.parent.parent / "cka"))
        self.project = paths.backends_dir() / "kubeadm" / "project"

    def main(self) -> KubeadmCluster:
        return KubeadmCluster("cka-kubeadm", self.project)

    def extra(self, index: int) -> KubeadmCluster:
        raise CkaError("the kubeadm backend provides one dedicated VM cluster")

    @property
    def max_extra_clusters(self) -> int:
        return 0

    def problems(self) -> list[str]:
        problems: list[str] = []
        if shutil.which("vagrant") is None:
            problems.append("vagrant is not installed")
        if shutil.which("virsh") is None and not Path("/dev/kvm").exists():
            problems.append("libvirt tooling or /dev/kvm is unavailable")
        if not self.source.is_dir():
            problems.append(f"kubeadm source project is missing: {self.source}")
        else:
            for name in ("Vagrantfile", "kubeadm-config.yaml", "scripts/provision-node"):
                if not (self.source / name).is_file():
                    problems.append(f"kubeadm source is missing {name}")
        try:
            self._prepare_project()
        except CkaError as exc:
            problems.append(str(exc))
        return sorted(set(problems))

    def prepare(self) -> Path:
        return self._prepare_project()

    def _prepare_project(self) -> Path:
        if (self.project / ".cka-project").is_file():
            return self.project
        if not self.source.is_dir():
            raise CkaError(f"kubeadm source project is missing: {self.source}")
        paths.ensure(self.project.parent)
        if self.project.exists():
            raise SafetyError(f"refusing to adopt existing directory {self.project} without .cka-project marker")
        shutil.copytree(self.source, self.project)
        # The source lab's 192.168.250.0/24 is intentionally reserved for the user's
        # hand-managed lab; this project owns the adjacent network.
        for path in (self.project / "Vagrantfile", self.project / "kubeadm-config.yaml", self.project / "scripts/provision-node"):
            text = path.read_text()
            path.write_text(text.replace("192.168.250", toolchain().kubeadm.network_prefix))
        config = self.project / "kubeadm-config.yaml"
        text = config.read_text()
        if "kubernetesVersion:" not in text:
            text = text.replace("kind: ClusterConfiguration\n", f"kind: ClusterConfiguration\nkubernetesVersion: v{toolchain().kubeadm.kubernetes_version}\n")
        config.write_text(text)
        (self.project / ".cka-project").write_text("cka-kubeadm\n")
        return self.project
