from pathlib import Path

from cka_labs.engine import catalog
from cka_labs.engine.exam import _points, _select
from cka_labs.engine.progress import Progress


def test_exam_selection_is_reproducible_and_weighted() -> None:
    labs = [source.meta() for source in catalog.discover().values() if "kind" in source.meta().backends]
    first = _select(labs, 17, 8)
    second = _select(labs, 17, 8)
    assert [lab.id for lab in first] == [lab.id for lab in second]
    # A lab counts toward its domain in the exam's certification, not its primary domain.
    domains = [lab.domain_in("cka") for lab in first]
    assert {d: domains.count(d) for d in set(domains)} == {
        "architecture": 2, "workloads": 1, "networking": 2, "storage": 1, "troubleshooting": 2,
    }


def test_exam_selection_counts_labs_toward_their_ckad_domain() -> None:
    labs = [source.meta() for source in catalog.discover().values() if "kind" in source.meta().backends]
    selected = _select(labs, 17, 8, "ckad")
    assert all("ckad" in lab.certs for lab in selected)
    counts = {d: sum(lab.domain_in("ckad") == d for lab in selected) for d in {lab.domain_in("ckad") for lab in selected}}
    assert counts == {"design-build": 2, "deployment": 2, "observability": 1, "environment": 2, "networking": 1}


def test_exam_selection_covers_cks_domains() -> None:
    labs = [source.meta() for source in catalog.discover().values() if "kind" in source.meta().backends]
    selected = _select(labs, 17, 8, "cks")
    counts = {d: sum(lab.domain_in("cks") == d for lab in selected) for d in {lab.domain_in("cks") for lab in selected}}
    assert counts == {
        "cluster-setup": 1,
        "cluster-hardening": 1,
        "system-hardening": 1,
        "microservice-vulnerabilities": 2,
        "supply-chain": 2,
        "runtime-security": 1,
    }


def test_exam_points_increase_with_difficulty() -> None:
    assert [_points(level) for level in range(1, 5)] == [5, 10, 15, 20]


def test_exam_report_is_persisted(tmp_path: Path) -> None:
    progress = Progress(tmp_path / "progress.db")
    exam_id = progress.start_exam(backend="kind", seed=3, duration_minutes=120, pass_percent=66)
    progress.finish_exam(exam_id, 70, 100, {"passed": True, "tasks": []})
    assert progress.exam_report(exam_id) == {"passed": True, "tasks": []}
