"""Lab requirements: pinned tools and shared cluster add-ons.

A lab lists what it needs in `requires`:
- a tool (`helm`): the pinned binary that `cka setup` installs must be present;
- a component from toolchain.yaml (`traefik`): installed once per cluster with Helm from
  a pinned, digest-checked chart, with its images loaded like lab images. It stays until
  the cluster is deleted; lab cleanup never touches it (see docs/safety.org).
"""

import json
import tempfile
from collections.abc import Callable

import yaml

from cka_labs import proc, tools
from cka_labs.backends.base import Cluster
from cka_labs.config import toolchain
from cka_labs.errors import CkaError

TOOLS = ("helm",)
COMPONENT_LABEL = "cka-labs.io/component"


def known() -> set[str]:
    return {*TOOLS, *toolchain().components}


def ensure(cluster: Cluster, requires: list[str], log: Callable[[str], None]) -> None:
    for name in requires:
        if name in TOOLS:
            _require_tool(name)
        elif name in toolchain().components:
            _install(cluster, name, log)
        else:
            raise CkaError(f"unknown requirement {name!r}; known: {', '.join(sorted(known()))}")


def _require_tool(name: str) -> None:
    if tools.installed_version(name) is None:
        raise CkaError(f"{name} is not installed; run `cka setup`")


def _install(cluster: Cluster, name: str, log: Callable[[str], None]) -> None:
    spec = toolchain().components[name]
    _require_tool("helm")
    admin = cluster.admin()
    admin.verify_marker()
    chart = tools.cache_chart(name, log)
    expected = chart.name.removesuffix(".tgz")
    helm_env = admin.env()
    listed = proc.run(
        ["helm", "list", "-n", spec.namespace, "--filter", f"^{spec.release}$", "-o", "json"], env=helm_env, timeout=60
    )
    releases: object = json.loads(listed.stdout or "[]") if listed.ok else []
    if isinstance(releases, list) and any(
        isinstance(r, dict) and r.get("chart") == expected and r.get("status") == "deployed" for r in releases
    ):
        return
    log(f"installing cluster component {name} ({expected}) into namespace {spec.namespace}")
    cluster.load_images(spec.images)
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", prefix=f"cka-{name}-") as values:
        yaml.safe_dump(spec.values, values)
        values.flush()
        proc.run(
            [
                "helm", "upgrade", "--install", spec.release, str(chart),
                "--namespace", spec.namespace, "--create-namespace",
                "--values", values.name, "--wait", "--timeout", "5m",
            ],
            env=helm_env,
            timeout=420,
            check=True,
        )
    admin.must(["label", "namespace", spec.namespace, f"{COMPONENT_LABEL}={name}", "--overwrite"])
