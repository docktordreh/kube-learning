from cka_labs.engine.progress import LabStats, ObjectiveStats
from cka_labs.engine.selection import filter_labs, recommend, weakest
from cka_labs.models import Lab


def lab(lab_id: str, objectives: list[str], difficulty: int, backends: tuple[str, ...] = ("kind",)) -> Lab:
    return Lab.model_validate(
        {
            "id": lab_id,
            "title": lab_id,
            "objectives": objectives,
            "difficulty": difficulty,
            "estimated_minutes": 5,
            "backends": list(backends),
            "namespaces": ["x"],
            "checks": [{"id": "a", "description": "d", "type": "exists", "resource": "pod/x", "namespace": "x"}],
            "hints": ["1", "2", "3"],
            "competencies": ["c"],
            "docs": ["https://kubernetes.io"],
        }
    )


LABS = [
    lab("networking-001", ["cka/networking/services", "ckad/networking/services"], 1),
    lab("networking-002", ["cka/networking/network-policies"], 3),
    lab("storage-001", ["cka/storage/pv-pvc"], 1),
    lab("architecture-009", ["cka/architecture/kubeadm"], 2, ("kubeadm",)),
]


def stats(objective: str, attempts: int, clean: int) -> ObjectiveStats:
    return ObjectiveStats(
        objective=objective, attempts=attempts, clean_passes=clean, credit=float(clean), weight=float(attempts),
        weighted_credit=float(clean), passes=clean, hints=0, avg_minutes=None, pace=None,
    )


def test_filters() -> None:
    assert [x.id for x in filter_labs(LABS, backend="kubeadm")] == ["architecture-009"]
    assert [x.id for x in filter_labs(LABS, backend="kind", cert="cka", domain="storage")] == ["storage-001"]
    assert [x.id for x in filter_labs(LABS, backend="kind", cert="ckad")] == ["networking-001"]
    assert [x.id for x in filter_labs(LABS, backend="kind", cert="ckad", domain="networking")] == ["networking-001"]
    assert [x.id for x in filter_labs(LABS, backend="kind", difficulty=3)] == ["networking-002"]


def test_recommend_starts_at_fundamentals() -> None:
    labs = filter_labs(LABS, backend="kind")
    choice = recommend(labs, {}, {})
    assert choice.lab.difficulty == 1


def test_recommend_unlocks_next_level_after_clean_pass() -> None:
    labs = filter_labs(LABS, backend="kind")
    objective_stats = {
        "cka/networking/services": stats("cka/networking/services", 1, 1),
        "cka/storage/pv-pvc": stats("cka/storage/pv-pvc", 1, 1),
    }
    lab_stats = {
        "networking-001": LabStats("networking-001", 1, 1, 1.0),
        "storage-001": LabStats("storage-001", 1, 1, 1.0),
    }
    # networking level is 1, so difficulty 3 is still locked; untried objectives are 0.5.
    choice = recommend(labs, objective_stats, lab_stats, cert="cka")
    assert choice.lab.id in {"networking-001", "storage-001"}


def test_recommend_ignores_objectives_of_other_certifications() -> None:
    labs = filter_labs(LABS, backend="kind")
    objective_stats = {
        "cka/networking/services": stats("cka/networking/services", 3, 3),
        "cka/storage/pv-pvc": stats("cka/storage/pv-pvc", 1, 0),
    }
    # Without a cert, networking-001's untried CKAD objective (0.5) would outrank storage.
    assert recommend(labs, objective_stats, {}, cert="cka").lab.id == "storage-001"


def test_weakest_targets_worst_attempted_objective() -> None:
    labs = filter_labs(LABS, backend="kind")
    objective_stats = {
        "cka/networking/services": stats("cka/networking/services", 4, 3),
        "cka/storage/pv-pvc": stats("cka/storage/pv-pvc", 3, 0),
    }
    choice = weakest(labs, objective_stats, {})
    assert choice.lab.id == "storage-001"
    assert "cka/storage/pv-pvc" in choice.reason


def test_weakest_without_history_falls_back() -> None:
    labs = filter_labs(LABS, backend="kind")
    assert weakest(labs, {}, {}).lab.difficulty == 1
