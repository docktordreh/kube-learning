"""Filesystem locations. Everything cka writes lives under one data directory.

Override with CKA_LABS_HOME (tests use this to isolate state).
"""

import os
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent


def home() -> Path:
    override = os.environ.get("CKA_LABS_HOME")
    if override:
        return Path(override).expanduser()
    xdg = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(xdg) / "cka-labs"


def bin_dir() -> Path:
    return home() / "bin"


def kubeconfig_dir() -> Path:
    return home() / "kubeconfig"


def state_dir() -> Path:
    return home() / "state"


def backends_dir() -> Path:
    return home() / "backends"


def progress_db() -> Path:
    return home() / "progress.db"


def labs_dir() -> Path:
    """Lab catalog: CKA_LABS_DIR, else the repository checkout, else the installed copy."""
    override = os.environ.get("CKA_LABS_DIR")
    if override:
        return Path(override).expanduser()
    checkout = PACKAGE_DIR.parent.parent / "labs"
    if checkout.is_dir():
        return checkout
    return PACKAGE_DIR / "_labs"


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
