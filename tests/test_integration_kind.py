"""Lab conformance against a real disposable kind cluster.

Run:  uv run pytest -m integration            (all kind labs)
      CKA_LABS=networking-001,storage-001 uv run pytest -m integration

Uses the cka-managed cluster (`cka-labs`, or CKA_KIND_CLUSTER) and records nothing in
the user's progress history. Refuses to run while a lab or exam is active.
"""

import os

import pytest

from cka_labs.engine import catalog
from cka_labs.engine.conformance import verify_lab

pytestmark = pytest.mark.integration


def _kind_labs() -> list[str]:
    selected = os.environ.get("CKA_LABS")
    if selected:
        return selected.split(",")
    return sorted(s.id for s in catalog.discover().values() if "kind" in s.meta().backends)


@pytest.mark.parametrize("lab_id", _kind_labs())
def test_lab_conformance(lab_id: str) -> None:
    report = verify_lab(lab_id, "kind", seed=int(os.environ.get("CKA_SEED", "1")), log=lambda _: None)
    assert report.ok, "\n".join(report.lines)
