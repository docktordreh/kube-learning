"""Lab requirements: pinned tools and shared cluster add-ons.

A lab lists what it needs in `requires`:
- a tool (`helm`): the pinned binary that `cka setup` installs must be present;
- a component from toolchain.yaml (`traefik`, `gateway-api`), installed once per cluster
  from a pinned, digest-checked artifact after its own `requires`. Chart components are
  Helm releases (reinstalled when chart or values change); manifest components are
  applied server-side, which is a no-op when nothing changed. Components stay until the
  cluster is deleted; lab cleanup never touches them (see docs/safety.org).
"""

import json
import tempfile
from collections.abc import Callable

import yaml

from cka_labs import proc, tools
from cka_labs.backends.base import Cluster
from cka_labs.config import Component, toolchain
from cka_labs.errors import CkaError

TOOLS = ("helm",)
COMPONENT_LABEL = "cka-labs.io/component"

Log = Callable[[str], None]


def known() -> set[str]:
    return {*TOOLS, *toolchain().components}


def ensure(cluster: Cluster, requires: list[str], log: Log, _path: tuple[str, ...] = ()) -> None:
    for name in requires:
        if name in _path:
            raise CkaError(f"component dependency cycle: {' -> '.join([*_path, name])}")
        if name in TOOLS:
            _require_tool(name)
        elif name in toolchain().components:
            spec = toolchain().components[name]
            ensure(cluster, spec.requires, log, (*_path, name))
            if spec.chart is not None:
                _install_chart(cluster, name, spec, log)
            else:
                _apply_manifest(cluster, name, log)
        else:
            raise CkaError(f"unknown requirement {name!r}; known: {', '.join(sorted(known()))}")


def _require_tool(name: str) -> None:
    if tools.installed_version(name) is None:
        raise CkaError(f"{name} is not installed; run `cka setup`")


def _apply_manifest(cluster: Cluster, name: str, log: Log) -> None:
    admin = cluster.admin()
    admin.verify_marker()
    manifest = tools.cache_artifact(name, log)
    admin.must(["apply", "--server-side", "--force-conflicts", f"--field-manager=cka-{name}", "-f", str(manifest)], timeout=180)


def _install_chart(cluster: Cluster, name: str, spec: Component, log: Log) -> None:
    _require_tool("helm")
    admin = cluster.admin()
    admin.verify_marker()
    chart = tools.cache_artifact(name, log)
    expected = chart.name.removesuffix(".tgz")
    helm_env = admin.env()
    if _deployed(spec, expected, helm_env):
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


def _deployed(spec: Component, chart: str, helm_env: dict[str, str]) -> bool:
    """Whether the release is deployed from this chart with exactly these values."""
    namespace = ["--namespace", spec.namespace]
    listed = proc.run(["helm", "list", *namespace, "--filter", f"^{spec.release}$", "-o", "json"], env=helm_env, timeout=60)
    releases: object = json.loads(listed.stdout or "[]") if listed.ok else []
    if not isinstance(releases, list) or not any(
        isinstance(r, dict) and r.get("chart") == chart and r.get("status") == "deployed" for r in releases
    ):
        return False
    values = proc.run(["helm", "get", "values", spec.release, *namespace, "-o", "json"], env=helm_env, timeout=60)
    return values.ok and json.loads(values.stdout or "null") == json.loads(json.dumps(spec.values))
