"""Static lab validation (no cluster needed). Run by `cka dev validate` and the unit tests."""

import itertools
import re

from cka_labs.config import curriculum, toolchain
from cka_labs.engine import catalog
from cka_labs.engine.catalog import LabSource
from cka_labs.errors import CkaError
from cka_labs.models import ApplyStep

REQUIRED_FILES = ("lab.yaml", "task.md", "solution.sh", "explanation.md")
IMAGE_LINE = re.compile(r"^\s*-?\s*image:\s*[\"']?([^\s\"'#]+)")
# A manifest line carrying this marker may reference an image outside the offline set
# (e.g. a deliberately non-existent tag for an ImagePullBackOff scenario).
ALLOW_IMAGE_MARKER = "cka: unlisted-image"
MIN_HINTS = 3


def normalise_image(image: str) -> str:
    name = image if "/" in image.split(":")[0] else f"library/{image}"
    first = name.split("/")[0]
    return name if "." in first or ":" in first else f"docker.io/{name}"


def _combinations(source: LabSource) -> list[dict[str, str]]:
    choices = source.param_choices
    names = sorted(choices)
    combos = [dict(zip(names, combo, strict=True)) for combo in itertools.product(*(choices[n] for n in names))]
    return combos[:64] or [{}]


def validate_lab(source: LabSource) -> list[str]:
    problems: list[str] = []
    prefix = source.id
    for name in REQUIRED_FILES:
        if not source.has(name):
            problems.append(f"{prefix}: missing {name}")
    if problems:
        return problems
    try:
        lab = source.meta()
    except CkaError as exc:
        return [f"{prefix}: {exc}"]

    if source.directory.parent.name != lab.domain:
        problems.append(f"{prefix}: lives in labs/{source.directory.parent.name} but domain is {lab.domain}")
    known = curriculum().objective_ids()
    problems += [f"{prefix}: unknown objective {o}" for o in lab.objectives if o not in known]
    if len(lab.hints) < MIN_HINTS:
        problems.append(f"{prefix}: needs at least {MIN_HINTS} progressive hints")
    problems += [f"{prefix}: docs must be https URLs: {d}" for d in lab.docs if not d.startswith("https://")]
    if lab.isolation == "namespace" and not (lab.namespaces or lab.owned):
        problems.append(f"{prefix}: namespace-isolated labs must declare the namespaces or resources they own")

    allowed_images = {normalise_image(i) for i in toolchain().images}
    for params in _combinations(source):
        values = source.placeholder_values(params)
        try:
            rendered = source.load(values)
            for name in ("task.md", "solution.sh", "explanation.md"):
                text = source.read(name, values)
                if "{{" in text:
                    problems.append(f"{prefix}: {name} references deferred values (captured.*)")
            for step in [*rendered.setup, *rendered.cleanup]:
                if isinstance(step, ApplyStep):
                    if not (source.directory / step.apply).is_file():
                        problems.append(f"{prefix}: missing manifest {step.apply}")
                        continue
                    for line in source.read(step.apply, values).splitlines():
                        match = IMAGE_LINE.match(line)
                        if match and ALLOW_IMAGE_MARKER not in line:
                            image = normalise_image(match.group(1))
                            if image not in allowed_images:
                                problems.append(f"{prefix}: image {match.group(1)} not in toolchain.yaml images")
        except CkaError as exc:
            problems.append(f"{prefix} with {values}: {exc}")
    return sorted(set(problems))


def validate_all() -> list[str]:
    problems: list[str] = []
    for source in catalog.discover().values():
        problems += validate_lab(source)
    return problems
