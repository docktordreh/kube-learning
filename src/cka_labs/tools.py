"""Install pinned kind and kubectl into the cka bin directory and pre-pull lab images.

Binaries are verified against the SHA-256 files published next to them by the upstream
projects. Nothing is installed system-wide.
"""

import hashlib
import platform
import shutil
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from cka_labs import paths, proc
from cka_labs.config import toolchain
from cka_labs.errors import CkaError


@dataclass(frozen=True)
class Download:
    name: str
    version: str
    url: str
    sha256_url: str


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
    return [
        Download("kind", tc.kind.version, kind_url, kind_url + ".sha256sum"),
        Download("kubectl", tc.kubectl.version, kubectl_url, kubectl_url + ".sha256"),
    ]


def installed_version(name: str) -> str | None:
    binary = paths.bin_dir() / name
    if not binary.is_file():
        return None
    argv = [str(binary), "version"] if name == "kind" else [str(binary), "version", "--client"]
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
    target = paths.ensure(paths.bin_dir()) / download.name
    temporary = target.with_suffix(".partial")
    temporary.write_bytes(payload)
    temporary.chmod(0o755)
    temporary.replace(target)
    log(f"installed {target} (sha256 {actual[:16]}…)")


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
