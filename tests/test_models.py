import pytest
from pydantic import ValidationError

from cka_labs.models import ExecCheck, JsonPathCheck, Lab

EXISTS = {"id": "a", "description": "d", "type": "exists", "resource": "pod/x", "namespace": "x"}
BASE = {
    "id": "networking-999",
    "title": "t",
    "domain": "networking",
    "objectives": ["networking/services"],
    "difficulty": 2,
    "estimated_minutes": 5,
    "backends": ["kind"],
    "namespaces": ["x"],
    "checks": [EXISTS],
    "hints": ["1", "2", "3"],
    "competencies": ["c"],
    "docs": ["https://kubernetes.io"],
}


def test_minimal_lab_parses() -> None:
    lab = Lab.model_validate(BASE)
    assert lab.goal_checks[0].id == "a"


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Lab.model_validate({**BASE, "surprise": 1})


def test_needs_a_goal() -> None:
    with pytest.raises(ValidationError, match="goal"):
        Lab.model_validate({**BASE, "checks": [{**EXISTS, "role": "guard"}]})


def test_duplicate_check_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="unique"):
        Lab.model_validate({**BASE, "checks": [EXISTS, EXISTS]})


def test_owned_must_be_explicit() -> None:
    with pytest.raises(ValidationError, match="explicit"):
        Lab.model_validate({**BASE, "owned": ["namespace"]})
    with pytest.raises(ValidationError, match="explicit"):
        Lab.model_validate({**BASE, "owned": ["namespace/*"]})


def test_jsonpath_value_required_for_comparisons() -> None:
    with pytest.raises(ValidationError):
        JsonPathCheck.model_validate({"type": "jsonpath", "resource": "pod/x", "jsonpath": "{.a}", "op": "equals"})
    JsonPathCheck.model_validate({"type": "jsonpath", "resource": "pod/x", "jsonpath": "{.a}", "op": "nonempty"})


def test_exec_needs_one_target() -> None:
    with pytest.raises(ValidationError):
        ExecCheck.model_validate({"type": "exec", "namespace": "n", "command": ["true"]})
    with pytest.raises(ValidationError):
        ExecCheck.model_validate({"type": "exec", "namespace": "n", "pod": "p", "selector": "a=b", "command": ["true"]})


def test_string_numbers_from_templates_are_coerced() -> None:
    lab = Lab.model_validate(
        {
            **BASE,
            "checks": [
                {"id": "r", "description": "d", "type": "deployment_ready", "namespace": "x", "name": "y", "replicas": "3"}
            ],
        }
    )
    assert lab.checks[0].model_dump()["replicas"] == 3
