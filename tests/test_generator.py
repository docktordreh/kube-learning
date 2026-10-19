import pytest

from cka_labs.engine.generator import choose_params, render_text, render_tree, to_json
from cka_labs.errors import CkaError


def test_same_seed_same_scenario() -> None:
    params = {"ns": ["a", "b", "c"], "app": ["x", "y"]}
    assert choose_params("lab-001", params, 42) == choose_params("lab-001", params, 42)


def test_seed_is_scoped_per_lab() -> None:
    params = {"ns": [str(i) for i in range(50)]}
    picks = {choose_params(f"lab-{i:03d}", params, 7)["ns"] for i in range(20)}
    assert len(picks) > 1


def test_render_is_strict() -> None:
    assert render_text("ns={{ ns }}", {"ns": "shop"}) == "ns=shop"
    with pytest.raises(CkaError, match="unknown value"):
        render_text("{{missing}}", {})


def test_captured_values_can_be_deferred() -> None:
    assert render_text("{{captured.gen}}", {}, defer_captured=True) == "{{captured.gen}}"
    with pytest.raises(CkaError):
        render_text("{{captured.gen}}", {})


def test_render_tree_leaves_keys_and_scalars() -> None:
    tree = to_json({"{{k}}": ["{{v}}", 3, True, None]})
    assert render_tree(tree, {"v": "1", "k": "x"}) == {"{{k}}": ["1", 3, True, None]}


def test_to_json_rejects_non_json_yaml_values() -> None:
    import datetime

    with pytest.raises(CkaError):
        to_json({"when": datetime.date(2026, 1, 1)})
