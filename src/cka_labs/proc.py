"""Subprocess execution. argv lists only; shells are invoked explicitly when a script is intended."""

import os
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from cka_labs import paths
from cka_labs.errors import CkaError


@dataclass(frozen=True)
class Result:
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    def output(self) -> str:
        return (self.stdout + self.stderr).strip()


def tool_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Environment with cka-managed binaries first on PATH."""
    env = dict(os.environ)
    env["PATH"] = f"{paths.bin_dir()}{os.pathsep}{env.get('PATH', '')}"
    # kubectl's discovery cache defaults to ~/.kube/cache; keep it inside the cka directory.
    env["KUBECACHEDIR"] = str(paths.home() / "cache" / "kube")
    if extra:
        env.update(extra)
    return env


def run(
    argv: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    stdin: str | None = None,
    timeout: float = 120,
    check: bool = False,
) -> Result:
    try:
        completed = subprocess.run(
            list(argv),
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=tool_env(env),
        )
    except FileNotFoundError as exc:
        raise CkaError(f"command not found: {argv[0]} (run `cka setup`)") from exc
    except subprocess.TimeoutExpired as exc:
        result = Result(tuple(argv), 124, _text(exc.stdout), _text(exc.stderr) + f"\ntimed out after {timeout}s")
        if check:
            raise CkaError(f"timed out after {timeout}s: {' '.join(argv)}") from exc
        return result
    result = Result(tuple(argv), completed.returncode, completed.stdout, completed.stderr)
    if check and not result.ok:
        raise CkaError(f"command failed ({result.returncode}): {' '.join(argv)}\n{result.output()}")
    return result


def interactive(argv: Sequence[str], *, env: Mapping[str, str] | None = None) -> int:
    """Run attached to the terminal (student shells, ssh)."""
    try:
        return subprocess.run(list(argv), env=tool_env(env)).returncode
    except FileNotFoundError as exc:
        raise CkaError(f"command not found: {argv[0]} (run `cka setup`)") from exc


def _text(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    return value
