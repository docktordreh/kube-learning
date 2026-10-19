from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> Path:
    """Unit tests never see the user's cka state. Integration tests use the real home
    (they need the cached tools and cluster) but run against cka-managed clusters only."""
    if request.node.get_closest_marker("integration") or request.node.get_closest_marker("kubeadm"):
        return Path.home()
    home = tmp_path / "cka-home"
    monkeypatch.setenv("CKA_LABS_HOME", str(home))
    return home
