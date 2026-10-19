"""Lab discovery and loading.

Layout: labs/<domain>/<lab-id>/{lab.yaml, task.md, solution.sh, explanation.md, manifests/...}
"""

from collections.abc import Mapping
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
import yaml
from pydantic import ValidationError

from cka_labs import paths
from cka_labs.engine.generator import Json, choose_params, render_text, render_tree, to_json
from cka_labs.errors import CkaError
from cka_labs.models import Lab

# Logical node names used by labs; backends map them to real node names.
LOGICAL_NODES = ("controlplane", "worker1", "worker2")
PLACEHOLDER_NODES = {f"node.{n}": n for n in LOGICAL_NODES}


@dataclass(frozen=True)
class LabSource:
    id: str
    directory: Path

    @cached_property
    def raw(self) -> dict[str, Json]:
        with (self.directory / "lab.yaml").open() as handle:
            loaded: object = yaml.safe_load(handle)
        tree = to_json(loaded)
        if not isinstance(tree, dict):
            raise CkaError(f"{self.directory}/lab.yaml must be a mapping")
        return tree

    @property
    def param_choices(self) -> dict[str, list[str]]:
        params = self.raw.get("params") or {}
        if not isinstance(params, dict):
            raise CkaError(f"{self.id}: params must be a mapping")
        result: dict[str, list[str]] = {}
        for name, spec in params.items():
            choices = spec.get("choices") if isinstance(spec, dict) else None
            if not isinstance(choices, list) or not choices:
                raise CkaError(f"{self.id}: param {name} needs a non-empty choices list")
            result[name] = [str(c) for c in choices]
        return result

    def values(self, seed: int, nodes: Mapping[str, str]) -> dict[str, str]:
        values = choose_params(self.id, self.param_choices, seed)
        values.update({f"node.{logical}": actual for logical, actual in nodes.items()})
        values["lab.id"] = self.id
        values["workdir"] = str(workdir(self.id))
        return values

    def load(self, values: Mapping[str, str]) -> Lab:
        rendered = render_tree(self.raw, values, defer_captured=True)
        try:
            lab = Lab.model_validate(rendered)
        except ValidationError as exc:
            raise CkaError(f"{self.id}: invalid lab.yaml\n{exc}") from exc
        if lab.id != self.id:
            raise CkaError(f"{self.directory}: lab id {lab.id!r} does not match directory name")
        return lab

    def meta(self) -> Lab:
        """The lab rendered with each parameter's first choice (for listing and validation)."""
        return self.load(self.placeholder_values())

    def placeholder_values(self, params: Mapping[str, str] | None = None) -> dict[str, str]:
        values = dict(params) if params is not None else {n: c[0] for n, c in self.param_choices.items()}
        values.update(PLACEHOLDER_NODES)
        values["lab.id"] = self.id
        values["workdir"] = str(workdir(self.id))
        return values

    def read(self, name: str, values: Mapping[str, str]) -> str:
        return render_text((self.directory / name).read_text(), values, defer_captured=True)

    def has(self, name: str) -> bool:
        return (self.directory / name).is_file()


def workdir(lab_id: str) -> Path:
    """Host directory for files a task asks the student to read or write."""
    return paths.home() / "work" / lab_id


def discover(root: Path | None = None) -> dict[str, LabSource]:
    root = root or paths.labs_dir()
    sources: dict[str, LabSource] = {}
    for lab_file in sorted(root.glob("*/*/lab.yaml")):
        directory = lab_file.parent
        source = LabSource(directory.name, directory)
        if source.id in sources:
            raise CkaError(f"duplicate lab id {source.id}")
        sources[source.id] = source
    return sources


def get(lab_id: str, root: Path | None = None) -> LabSource:
    sources = discover(root)
    if lab_id not in sources:
        raise CkaError(f"unknown lab {lab_id!r}; see `cka lab list`")
    return sources[lab_id]
