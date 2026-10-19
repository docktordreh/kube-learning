"""Static validation of every lab in the catalog (schema, curriculum, files, images)."""

import pytest

from cka_labs.config import curriculum, toolchain
from cka_labs.engine import catalog
from cka_labs.engine.validation import normalise_image, validate_lab

SOURCES = catalog.discover()


def test_catalog_is_not_empty() -> None:
    assert len(SOURCES) >= 5


@pytest.mark.parametrize("lab_id", sorted(SOURCES))
def test_lab_is_valid(lab_id: str) -> None:
    assert validate_lab(SOURCES[lab_id]) == []


def test_every_domain_has_labs() -> None:
    domains = {source.meta().domain for source in SOURCES.values()}
    assert domains == {d.id for d in curriculum().domains}


def test_curriculum_weights_sum_to_100() -> None:
    assert sum(d.weight for d in curriculum().domains) == 100


def test_kubernetes_version_is_consistent() -> None:
    assert toolchain().kubeadm.kubernetes_version.startswith(curriculum().kubernetes_version + ".")
    assert toolchain().kubectl.version.startswith(f"v{curriculum().kubernetes_version}.")


def test_image_normalisation() -> None:
    assert normalise_image("busybox:1.37") == "docker.io/library/busybox:1.37"
    assert normalise_image("docker.io/library/busybox:1.37") == "docker.io/library/busybox:1.37"
    assert normalise_image("registry.k8s.io/pause:3.10") == "registry.k8s.io/pause:3.10"


def test_cluster_isolated_labs_are_marked() -> None:
    """Labs that touch nodes or the control plane must not share a cluster in exams."""
    for source in SOURCES.values():
        lab = source.meta()
        touches_nodes = any(hasattr(step, "node") for step in [*lab.setup, *lab.cleanup])
        if touches_nodes:
            assert lab.isolation == "cluster", f"{lab.id} runs node steps but is namespace-isolated"
