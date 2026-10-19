"""Deterministic, explainable lab selection for adaptive practice.

recommended: among labs at most one difficulty level above what you have cleanly passed in
             that domain, pick the one whose weakest objective is weakest.
weakest:     pick the objective with the highest weakness that you have attempted, then the
             least-practised lab covering it (falls back to recommended if nothing attempted).
Ties: fewer attempts of the lab, older last attempt, lower difficulty, lab id.
"""

from collections.abc import Iterable
from dataclasses import dataclass

from cka_labs.engine.progress import LabStats, ObjectiveStats
from cka_labs.errors import CkaError
from cka_labs.models import Lab

UNTRIED_WEAKNESS = 0.5


@dataclass(frozen=True)
class Choice:
    lab: Lab
    reason: str


def filter_labs(
    labs: Iterable[Lab], *, backend: str, domain: str | None = None, difficulty: int | None = None
) -> list[Lab]:
    return [
        lab
        for lab in labs
        if backend in lab.backends
        and (domain is None or lab.domain == domain)
        and (difficulty is None or lab.difficulty == difficulty)
    ]


def _weakness(objective: str, stats: dict[str, ObjectiveStats]) -> float:
    return stats[objective].weakness if objective in stats else UNTRIED_WEAKNESS


def _tiebreak(lab: Lab, lab_stats: dict[str, LabStats]) -> tuple[int, float, int, str]:
    s = lab_stats.get(lab.id)
    return (s.attempts if s else 0, (s.last_attempt or 0.0) if s else 0.0, lab.difficulty, lab.id)


def _levels(labs: list[Lab], lab_stats: dict[str, LabStats]) -> dict[str, int]:
    level: dict[str, int] = {}
    for lab in labs:
        s = lab_stats.get(lab.id)
        if s and s.clean_passes:
            level[lab.domain] = max(level.get(lab.domain, 0), lab.difficulty)
    return level


def recommend(labs: list[Lab], stats: dict[str, ObjectiveStats], lab_stats: dict[str, LabStats]) -> Choice:
    if not labs:
        raise CkaError("no lab matches the requested filters on this backend")
    levels = _levels(labs, lab_stats)
    reachable = [lab for lab in labs if lab.difficulty <= levels.get(lab.domain, 0) + 1] or labs

    def key(lab: Lab) -> tuple[float, tuple[int, float, int, str]]:
        return (-max(_weakness(o, stats) for o in lab.objectives), _tiebreak(lab, lab_stats))

    lab = min(reachable, key=key)
    objective = max(lab.objectives, key=lambda o: _weakness(o, stats))
    return Choice(
        lab,
        f"objective {objective} has weakness {_weakness(objective, stats):.2f}; "
        f"difficulty {lab.difficulty} is within your current level +1 in {lab.domain}",
    )


def weakest(labs: list[Lab], stats: dict[str, ObjectiveStats], lab_stats: dict[str, LabStats]) -> Choice:
    covered = {o for lab in labs for o in lab.objectives}
    attempted = [s for s in stats.values() if s.objective in covered]
    if not attempted:
        return recommend(labs, stats, lab_stats)
    target = max(attempted, key=lambda s: (s.weakness, -s.clean_passes, s.objective))
    lab = min((lab for lab in labs if target.objective in lab.objectives), key=lambda lab: _tiebreak(lab, lab_stats))
    return Choice(
        lab,
        f"weakest objective {target.objective}: {target.clean_passes}/{target.attempts} clean passes "
        f"(weakness {target.weakness:.2f})",
    )
