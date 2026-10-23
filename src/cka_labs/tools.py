"""Install pinned kind, kubectl and helm into the cka bin directory, cache component charts
and pre-pull lab images.

Binaries are verified against the SHA-256 files published next to them by the upstream
projects. Nothing is installed system-wide.
"""

import hashlib
import io
import platform
import tarfile
import shutil
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from cka_labs import paths, proc
from cka_labs.config import toolchain
from cka_labs.errors import CkaError


@dataclass(frozen=True)
class Download:
    name: str
    version: str
    url: str
    sha256_url: str
    member: str | None = None  # path of the binary inside a .tar.gz download


def platform_pair() -> tuple[str, str]:
    system = {"linux": "linux", "darwin": "darwin"}.get(sys.platform)
    machine = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(
        platform.machine().lower()
    )
    if system is None or machine is None:
        raise CkaError(f"unsupported platform {sys.platform}/{platform.machine()} (linux|darwin, amd64|arm64)")
    return system, machine


def downloads() -> list[Download]:
    system, machine = platform_pair()
    tc = toolchain()
    kind_url = f"https://github.com/kubernetes-sigs/kind/releases/download/{tc.kind.version}/kind-{system}-{machine}"
    kubectl_url = f"https://dl.k8s.io/release/{tc.kubectl.version}/bin/{system}/{machine}/kubectl"
    helm_url = f"https://get.helm.sh/helm-{tc.helm.version}-{system}-{machine}.tar.gz"
    return [
        Download("kind", tc.kind.version, kind_url, kind_url + ".sha256sum"),
        Download("kubectl", tc.kubectl.version, kubectl_url, kubectl_url + ".sha256"),
        Download("helm", tc.helm.version, helm_url, helm_url + ".sha256sum", f"{system}-{machine}/helm"),
    ]


def installed_version(name: str) -> str | None:
    binary = paths.bin_dir() / name
    if not binary.is_file():
        return None
    argv = {"kind": [str(binary), "version"], "helm": [str(binary), "version", "--short"]}.get(
        name, [str(binary), "version", "--client"]
    )
    result = proc.run(argv, timeout=20)
    return result.stdout.strip() if result.ok else None


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "cka-labs"})
    with urllib.request.urlopen(request, timeout=120) as response:
        data: bytes = response.read()
    return data


def install(download: Download, log: Callable[[str], None]) -> None:
    current = installed_version(download.name)
    if current and download.version in current:
        log(f"{download.name} {download.version} already installed")
        return
    log(f"downloading {download.url}")
    payload = _fetch(download.url)
    expected = _fetch(download.sha256_url).decode().split()[0].strip().lower()
    actual = hashlib.sha256(payload).hexdigest()
    if actual != expected:
        raise CkaError(f"{download.name}: checksum mismatch (expected {expected}, got {actual})")
    if download.member:
        with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
            member = archive.extractfile(download.member)
            if member is None:
                raise CkaError(f"{download.url} has no {download.member}")
            payload = member.read()
    target = paths.ensure(paths.bin_dir()) / download.name
    temporary = target.with_suffix(".partial")
    temporary.write_bytes(payload)
    temporary.chmod(0o755)
    temporary.replace(target)
    log(f"installed {target} (sha256 {actual[:16]}…)")


def artifact_path(component: str) -> Path:
    spec = toolchain().components[component]
    return paths.home() / "components" / component / spec.url.rsplit("/", 1)[-1]


def cache_artifact(component: str, log: Callable[[str], None]) -> Path:
    """The component's pinned chart or manifest, downloaded once and verified against its digest."""
    spec = toolchain().components[component]
    target = artifact_path(component)
    if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == spec.sha256:
        return target
    log(f"downloading {spec.url}")
    payload = _fetch(spec.url)
    actual = hashlib.sha256(payload).hexdigest()
    if actual != spec.sha256:
        raise CkaError(f"{component}: checksum mismatch (expected {spec.sha256}, got {actual})")
    paths.ensure(target.parent)
    temporary = target.with_suffix(".partial")
    temporary.write_bytes(payload)
    temporary.replace(target)
    return target


def pull_images(log: Callable[[str], None]) -> None:
    if shutil.which("docker") is None:
        raise CkaError("docker is required to cache images for offline use")
    images = [toolchain().kind.node_image, *toolchain().images]
    for image in images:
        if proc.run(["docker", "image", "inspect", image], timeout=30).ok:
            log(f"cached {image}")
            continue
        log(f"pulling {image}")
        proc.run(["docker", "pull", image], timeout=1200, check=True)
