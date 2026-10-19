"""kubeadm backend (Vagrant/libvirt VMs). Implemented in phase 4."""

from cka_labs.backends.base import Backend, Cluster
from cka_labs.errors import CkaError


class KubeadmBackend(Backend):
    name = "kubeadm"

    def main(self) -> Cluster:
        raise CkaError("the kubeadm backend is not implemented yet")

    def extra(self, index: int) -> Cluster:
        raise CkaError("the kubeadm backend has no extra clusters")

    def problems(self) -> list[str]:
        return ["not implemented yet"]
