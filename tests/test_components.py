"""Pinned helm download, component chart cache and lab requirements (no cluster needed)."""

import hashlib
import io
import tarfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from cka_labs import paths, proc, tools
from cka_labs.config import Component, toolchain
from cka_labs.engine import catalog, components
from cka_labs.errors import CkaError


def _tarball(member: str, content: bytes) -> bytes:
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        info = tarfile.TarInfo(member)
        info.size = len(content)
        archive.addfile(info, io.BytesIO(content))
    return buffer.getvalue()


def test_helm_is_pinned_and_extracted_from_its_tarball(monkeypatch: pytest.MonkeyPatch) -> None:
    helm = next(d for d in tools.downloads() if d.name == "helm")
    assert helm.version == toolchain().helm.version
    assert helm.url.startswith("https://get.helm.sh/") and helm.sha256_url == helm.url + ".sha256sum"
    payload = _tarball(helm.member or "", b"#!/bin/sh\necho helm\n")
    files = {helm.url: payload, helm.sha256_url: f"{hashlib.sha256(payload).hexdigest()}  helm.tgz\n".encode()}
    monkeypatch.setattr(tools, "_fetch", files.__getitem__)
    monkeypatch.setattr(tools, "installed_version", lambda name: None)
    tools.install(helm, lambda _: None)
    assert (paths.bin_dir() / "helm").read_bytes() == b"#!/bin/sh\necho helm\n"


def test_chart_cache_verifies_the_digest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools, "_fetch", lambda url: b"tampered")
    with pytest.raises(CkaError, match="checksum mismatch"):
        tools.cache_artifact("traefik", lambda _: None)
    assert not tools.artifact_path("traefik").exists()


def test_component_images_are_in_the_offline_set() -> None:
    for spec in toolchain().components.values():
        assert set(spec.images) <= set(toolchain().images)


def test_helm_state_stays_in_the_cka_directory() -> None:
    env = proc.tool_env()
    for kind in ("CACHE", "CONFIG", "DATA"):
        assert Path(env[f"HELM_{kind}_HOME"]).is_relative_to(paths.home())


def test_requirements() -> None:
    assert components.known() >= {"helm", "traefik"}
    with pytest.raises(CkaError, match="unknown requirement"):
        components.ensure(None, ["nope"], lambda _: None)  # type: ignore[arg-type]
    with pytest.raises(CkaError, match="helm is not installed"):
        components.ensure(None, ["helm"], lambda _: None)  # type: ignore[arg-type]


def test_component_needs_exactly_one_source() -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        Component.model_validate({"sha256": "x"})
    with pytest.raises(ValidationError, match="release and a namespace"):
        Component.model_validate({"chart": "https://x/c.tgz", "sha256": "x"})
    assert Component.model_validate({"manifest": "https://x/m.yaml", "sha256": "x"}).url == "https://x/m.yaml"


def test_dependencies_are_installed_first(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(components, "_apply_manifest", lambda cluster, name, log: calls.append(name))
    monkeypatch.setattr(components, "_install_chart", lambda cluster, name, spec, log: calls.append(name))
    components.ensure(None, ["traefik"], lambda _: None)  # type: ignore[arg-type]
    assert calls == ["gateway-api", "traefik"]


def test_dependency_cycles_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    looped = {
        "a": Component(manifest="https://x/a.yaml", sha256="x", requires=["b"]),
        "b": Component(manifest="https://x/b.yaml", sha256="x", requires=["a"]),
    }
    monkeypatch.setattr(components, "toolchain", lambda: SimpleNamespace(components=looped))
    with pytest.raises(CkaError, match="cycle: a -> b -> a"):
        components.ensure(None, ["a"], lambda _: None)  # type: ignore[arg-type]


def test_labs_can_reference_their_own_directory() -> None:
    source = catalog.get("ckad-deployment-003")
    assert source.placeholder_values()["lab.dir"] == str(source.directory)
    assert (source.directory / "charts" / "web" / "Chart.yaml").is_file()
