"""Static validation of every lab in the catalog (schema, curriculum, files, images)."""

from pathlib import Path

import pytest

from cka_labs.config import curricula, curriculum, toolchain
from cka_labs.engine import catalog
from cka_labs.engine.catalog import LabSource
from cka_labs.engine.validation import normalise_image, validate_lab

SOURCES = catalog.discover()


def test_catalog_is_not_empty() -> None:
    assert len(SOURCES) >= 5


@pytest.mark.parametrize("lab_id", sorted(SOURCES))
def test_lab_is_valid(lab_id: str) -> None:
    assert validate_lab(SOURCES[lab_id]) == []


@pytest.mark.parametrize("cert", ["cka", "ckad"])
def test_every_domain_has_labs(cert: str) -> None:
    domains = {source.meta().domain_in(cert) for source in SOURCES.values()} - {None}
    assert domains == {d.id for d in curriculum(cert).domains}


@pytest.mark.parametrize("cert", sorted(curricula()))
def test_curriculum_weights_sum_to_100(cert: str) -> None:
    assert sum(d.weight for d in curriculum(cert).domains) == 100


def test_exam_quotas_follow_weights() -> None:
    assert curriculum("cka").quotas(8) == {
        "architecture": 2, "workloads": 1, "networking": 2, "storage": 1, "troubleshooting": 2,
    }
    for cert in curricula():
        assert sum(curriculum(cert).quotas(8).values()) == 8


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


def test_only_captured_tokens_count_as_deferred(tmp_path: Path) -> None:
    """Go templates ({{.Config.User}}) may appear in student-facing files; {{captured.x}} may not."""
    directory = tmp_path / "ckad" / "networking" / "ckad-networking-901"
    directory.mkdir(parents=True)
    (directory / "lab.yaml").write_text(
        "id: ckad-networking-901\ntitle: t\nobjectives: [ckad/networking/services]\ndifficulty: 1\n"
        "estimated_minutes: 5\nbackends: [kind]\nnamespaces: [x]\n"
        "checks: [{id: a, description: d, type: exists, resource: pod/x, namespace: x}]\n"
        "hints: ['1', '2', '3']\ncompetencies: [c]\ndocs: ['https://kubernetes.io']\n"
    )
    (directory / "task.md").write_text("docker inspect --format '{{.Config.User}}'\n")
    (directory / "solution.sh").write_text("echo {{captured.secret}}\n")
    (directory / "explanation.md").write_text("ok\n")
    problems = validate_lab(LabSource("ckad-networking-901", directory))
    assert problems == ["ckad-networking-901: solution.sh references deferred values (captured.*)"]
