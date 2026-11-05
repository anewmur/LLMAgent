
import copy
import json
from pathlib import Path
import pytest

from core.validate import validate_input

INPUT_PATH = Path(__file__).resolve().parent.parent / "input" / "input.json"


@pytest.fixture
def data():
    return json.loads(INPUT_PATH.read_text(encoding="utf-8"))


def find_point(data, pid):
    for p in data["points"]:
        if p["id"] == pid:
            return p
    raise KeyError(pid)


def test_original_input_has_no_problems(data):
    project, problems = validate_input(data)
    assert project is not None
    assert problems == []


def test_missing_axis_p3(data):
    changed = copy.deepcopy(data)
    del find_point(changed, "P3")["axis"]
    project, problems = validate_input(changed)
    assert any(p["where"] == "P3" and "axis" in p["message"] for p in problems)


def test_material_conflict(data):
    changed = copy.deepcopy(data)
    changed["pipe"]["material"] = "ПЭ 80"
    project, problems = validate_input(changed)
    assert any(p["where"] == "pipe" and "материал" in p["message"] for p in problems)


def test_bend_on_missing_point(data):
    changed = copy.deepcopy(data)
    changed["bends"][0]["at"] = "P9"
    project, problems = validate_input(changed)
    assert any(p["where"] == "P9" for p in problems)


def test_duplicate_point_id(data):
    changed = copy.deepcopy(data)
    changed["points"][1]["id"] = "P0"
    project, problems = validate_input(changed)
    assert any("повторяется" in p["message"] for p in problems)

