"""Curriculum and toolchain data, parsed once into typed models."""

from functools import cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from cka_labs import paths
from cka_labs.errors import CkaError

DATA_DIR = paths.PACKAGE_DIR / "data"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Domain(_Frozen):
    id: str
    title: str
    weight: int = Field(gt=0)
    objectives: dict[str, str]


class Curriculum(_Frozen):
    """One certification. Objective ids are <cert>/<domain>/<key>, cert being the file stem."""

    id: str
    exam: str
    kubernetes_version: str
    verified: str
    domains: list[Domain]

    def domain(self, domain_id: str) -> Domain:
        for domain in self.domains:
            if domain.id == domain_id:
                return domain
        raise CkaError(f"{self.id} has no domain {domain_id!r}")

    def objective_ids(self) -> set[str]:
        return {f"{self.id}/{d.id}/{o}" for d in self.domains for o in d.objectives}

    def quotas(self, count: int) -> dict[str, int]:
        """Split `count` exam tasks over the domains by weight (largest remainder, ties in file order)."""
        total = sum(d.weight for d in self.domains)
        quotas = {d.id: count * d.weight // total for d in self.domains}
        by_remainder = sorted(self.domains, key=lambda d: -(count * d.weight % total))
        for domain in by_remainder[: count - sum(quotas.values())]:
            quotas[domain.id] += 1
        return quotas


class KindTools(_Frozen):
    version: str
    node_image: str


class KubectlTools(_Frozen):
    version: str


class KubeadmTools(_Frozen):
    box: str
    box_version: str
    kubernetes_minor: str
    kubernetes_version: str
    upgrade_version: str
    crictl_version: str
    calico_version: str
    pod_subnet: str
    network_prefix: str


class HelmTools(_Frozen):
    version: str


class Component(_Frozen):
    """A shared cluster add-on that labs request via `requires` (see engine/components.py):
    a Helm chart installed as `release` into `namespace`, or a manifest applied server-side."""

    chart: str | None = None  # URL of the pinned chart archive
    manifest: str | None = None  # URL of the pinned manifest
    sha256: str
    release: str = ""
    namespace: str = ""
    images: list[str] = []
    values: dict[str, Any] = {}
    requires: list[str] = []  # components installed first

    @model_validator(mode="after")
    def _one_source(self) -> "Component":
        if (self.chart is None) == (self.manifest is None):
            raise ValueError("a component needs exactly one of chart or manifest")
        if self.chart is not None and not (self.release and self.namespace):
            raise ValueError("a chart component needs a release and a namespace")
        return self

    @property
    def url(self) -> str:
        return self.chart or self.manifest or ""


class Toolchain(_Frozen):
    kind: KindTools
    kubectl: KubectlTools
    helm: HelmTools
    kubeadm: KubeadmTools
    components: dict[str, Component] = {}
    images: list[str]


def _load(path: Path) -> object:
    with path.open() as handle:
        return yaml.safe_load(handle)


DEFAULT_CERT = "cka"


@cache
def curricula() -> dict[str, Curriculum]:
    """Every certification under data/curricula, keyed by id (cka, ckad, ...)."""
    loaded: dict[str, Curriculum] = {}
    for path in sorted((DATA_DIR / "curricula").glob("*.yaml")):
        data = _load(path)
        if not isinstance(data, dict):
            raise ValueError(f"{path} must be a mapping")
        loaded[path.stem] = Curriculum.model_validate({"id": path.stem, **data})
    return loaded


def curriculum(cert: str = DEFAULT_CERT) -> Curriculum:
    try:
        return curricula()[cert]
    except KeyError:
        raise CkaError(f"unknown certification {cert!r}: {', '.join(curricula())}") from None


def objective_ids() -> set[str]:
    return {o for c in curricula().values() for o in c.objective_ids()}


@cache
def toolchain() -> Toolchain:
    return Toolchain.model_validate(_load(DATA_DIR / "toolchain.yaml"))
