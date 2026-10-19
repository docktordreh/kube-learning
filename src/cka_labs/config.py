"""Curriculum and toolchain data, parsed once into typed models."""

from functools import cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

from cka_labs import paths

DATA_DIR = paths.PACKAGE_DIR / "data"


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Domain(_Frozen):
    id: str
    title: str
    weight: int = Field(gt=0)
    objectives: dict[str, str]


class Curriculum(_Frozen):
    exam: str
    kubernetes_version: str
    verified: str
    domains: list[Domain]

    def domain(self, domain_id: str) -> Domain:
        for domain in self.domains:
            if domain.id == domain_id:
                return domain
        raise KeyError(domain_id)

    def objective_ids(self) -> set[str]:
        return {f"{d.id}/{o}" for d in self.domains for o in d.objectives}

    def objective_title(self, objective_id: str) -> str:
        domain_id, _, key = objective_id.partition("/")
        return self.domain(domain_id).objectives[key]


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


class Toolchain(_Frozen):
    kind: KindTools
    kubectl: KubectlTools
    kubeadm: KubeadmTools
    images: list[str]


def _load(path: Path) -> object:
    with path.open() as handle:
        return yaml.safe_load(handle)


@cache
def curriculum() -> Curriculum:
    return Curriculum.model_validate(_load(DATA_DIR / "curriculum.yaml"))


@cache
def toolchain() -> Toolchain:
    return Toolchain.model_validate(_load(DATA_DIR / "toolchain.yaml"))
