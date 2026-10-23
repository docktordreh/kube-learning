"""Scenario generation: seeded parameter choice and strict {{name}} rendering.

The same (lab, seed) always yields the same scenario, so reset reproduces it exactly.
Rendering is strict: an unknown name is an authoring error, never an empty string.
Go/Helm template fields such as {{.Names}} start with a dot and are left untouched.
"""

import random
import re
from collections.abc import Mapping

from cka_labs.errors import CkaError

TOKEN = re.compile(r"\{\{\s*([A-Za-z0-9_][A-Za-z0-9_.]*)\s*\}\}")
# Values only known after setup (see CaptureStep); left in place until grading.
DEFERRED_PREFIX = "captured."

type Json = None | bool | int | float | str | list[Json] | dict[str, Json]


def choose_params(lab_id: str, params: Mapping[str, list[str]], seed: int) -> dict[str, str]:
    rng = random.Random(f"{lab_id}:{seed}")
    return {name: str(rng.choice(choices)) for name, choices in sorted(params.items())}


def render_text(text: str, values: Mapping[str, str], *, defer_captured: bool = False) -> str:
    def substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in values:
            return values[name]
        if defer_captured and name.startswith(DEFERRED_PREFIX):
            return match.group(0)
        raise CkaError(f"template references unknown value {{{{{name}}}}}")

    return TOKEN.sub(substitute, text)


def render_tree(tree: Json, values: Mapping[str, str], *, defer_captured: bool = False) -> Json:
    """Render every string inside parsed YAML (keys are never templated)."""
    match tree:
        case str():
            return render_text(tree, values, defer_captured=defer_captured)
        case list():
            return [render_tree(item, values, defer_captured=defer_captured) for item in tree]
        case dict():
            return {key: render_tree(value, values, defer_captured=defer_captured) for key, value in tree.items()}
        case _:
            return tree


def to_json(value: object) -> Json:
    """Narrow a yaml.safe_load result to the Json type (rejects dates, sets, non-string keys)."""
    match value:
        case None | bool() | int() | float() | str():
            return value
        case list():
            return [to_json(item) for item in value]
        case dict():
            result: dict[str, Json] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise CkaError(f"mapping keys must be strings, got {key!r}")
                result[key] = to_json(item)
            return result
        case _:
            raise CkaError(f"unsupported YAML value {value!r}; quote it")


def new_seed() -> int:
    return random.SystemRandom().randrange(1, 2**31)
