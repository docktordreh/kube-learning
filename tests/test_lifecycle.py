from types import SimpleNamespace

import pytest

from cka_labs.engine import lifecycle
from cka_labs.engine.lifecycle import ActiveLab, LabService, load_session, save_session
from cka_labs.engine.progress import Progress


def _service(monkeypatch: pytest.MonkeyPatch) -> LabService:
    lab = SimpleNamespace(
        id="networking-001", domain="networking", objectives=["networking/services"], difficulty=2,
        hints=["a", "b"], estimated_minutes=5,
    )
    runner = SimpleNamespace(captured={"node_ip": "1.2.3.4"}, cleanup=lambda: None)
    prepared = SimpleNamespace(lab=lab, runner=runner)
    monkeypatch.setattr(lifecycle, "provision", lambda prepared, log, **kwargs: None)
    monkeypatch.setattr(LabService, "_prepared", lambda self, session: prepared)
    return LabService(progress=Progress(), log=lambda _: None)


def _session(service: LabService, **update: object) -> ActiveLab:
    attempt = service.progress.start_attempt(
        lab_id="networking-001", mode="practice", backend="kind", seed=7,
        domain="networking", objectives=["networking/services"], difficulty=2, hints_total=2, estimated_minutes=5,
    )
    session = ActiveLab(
        lab_id="networking-001", backend="kind", cluster="cka-labs", seed=7,
        values={}, started_at=1.0, attempt_id=attempt,
    ).model_copy(update=update)
    save_session(session)
    return session


def test_reset_after_pass_starts_new_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch)
    first = _session(service, solved=True, hints_used=2)
    service.progress.finish_attempt(first.attempt_id, "passed")

    session = service.reset()

    assert session.attempt_id != first.attempt_id
    assert (session.solved, session.hints_used, session.solution_viewed) == (False, 0, False)
    assert session.started_at > first.started_at
    assert load_session() == session
    service.progress.record_solution_viewed(session.attempt_id)  # what `cka lab solution` records
    assert service.progress.lab_stats()["networking-001"].clean_passes == 1


def test_immediate_stop_is_not_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch)
    _session(service)

    service.stop()

    assert load_session() is None
    assert service.progress.lab_stats() == {}


def test_reset_before_pass_keeps_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(monkeypatch)
    first = _session(service, hints_used=1)

    session = service.reset()

    assert (session.attempt_id, session.hints_used, session.started_at) == (first.attempt_id, 1, first.started_at)


def test_cluster_isolation_uses_an_extra_cluster(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    class Cluster:
        backend_name = "kind"

        def __init__(self, name: str) -> None:
            self.name = name

        def ensure(self) -> None:
            calls.append(self.name)

    class Backend:
        max_extra_clusters = 1
        main_is_dedicated = False

        def __init__(self) -> None:
            self.main_cluster = Cluster("main")
            self.extra_cluster = Cluster("extra")

        def problems(self) -> list[str]:
            return []

        def main(self) -> Cluster:
            return self.main_cluster

        def extra(self, index: int) -> Cluster:
            assert index == 1
            return self.extra_cluster

    lab = SimpleNamespace(
        id="troubleshooting-007", domain="cka/troubleshooting", objectives=["cka/troubleshooting/kubelet"],
        difficulty=2, hints=["a"], estimated_minutes=5,
    )
    source = SimpleNamespace(meta=lambda: SimpleNamespace(backends=["kind"], isolation="cluster"))
    prepared = SimpleNamespace(lab=lab, values={}, runner=SimpleNamespace(captured={}))
    backend = Backend()
    monkeypatch.setattr(lifecycle, "get_backend", lambda name: backend)
    monkeypatch.setattr(lifecycle.catalog, "get", lambda lab_id: source)
    monkeypatch.setattr(lifecycle, "prepare", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(lifecycle, "provision", lambda *args, **kwargs: None)

    LabService(progress=Progress(), log=lambda _: None).start("troubleshooting-007", "kind", seed=1)

    assert calls == ["extra"]
