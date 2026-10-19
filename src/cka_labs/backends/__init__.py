from cka_labs.backends.base import Backend, Cluster
from cka_labs.errors import CkaError
from cka_labs.models import Backend as BackendName


def get_backend(name: BackendName | str) -> Backend:
    # Imported lazily so that one backend's tooling is never required by the other.
    if name == "kind":
        from cka_labs.backends.kind import KindBackend

        return KindBackend()
    if name == "kubeadm":
        from cka_labs.backends.kubeadm import KubeadmBackend

        return KubeadmBackend()
    raise CkaError(f"unknown backend {name!r} (kind, kubeadm)")


__all__ = ["Backend", "Cluster", "get_backend"]
