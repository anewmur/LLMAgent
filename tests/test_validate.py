import copy

import pytest

from core.validate import validate_input


def find_point(data, pid):
    for p in data["points"]:
        if p["id"] == pid:
            return p
    raise KeyError(pid)


def test_original_input_has_no_problems(route_data):
    project, problems = validate_input(route_data)
    assert project is not None
    assert problems == []


def test_missing_axis_p3(route_data):
    changed = copy.deepcopy(route_data)
    del find_point(changed, "P3")["axis"]
    project, problems = validate_input(changed)
    assert any(p["where"] == "P3" and "axis" in p["message"] for p in problems)


def test_material_conflict(route_data):
    changed = copy.deepcopy(route_data)
    changed["pipe"]["material"] = "\u041f\u042d 80"
    project, problems = validate_input(changed)
    assert any(p["where"] == "pipe" and "\u043c\u0430\u0442\u0435\u0440\u0438\u0430\u043b" in p["message"] for p in problems)


def test_bend_on_missing_point(route_data):
    changed = copy.deepcopy(route_data)
    changed["bends"][0]["at"] = "P9"
    project, problems = validate_input(changed)
    assert any(p["where"] == "P9" for p in problems)


def test_duplicate_point_id(route_data):
    changed = copy.deepcopy(route_data)
    changed["points"][1]["id"] = "P0"
    project, problems = validate_input(changed)
    assert any("\u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0435\u0442\u0441\u044f" in p["message"] for p in problems)


def test_coincident_neighboring_points(route_data):
    changed = copy.deepcopy(route_data)
    start = find_point(changed, "P0")
    end = find_point(changed, "P1")
    end["x"], end["y"] = start["x"], start["y"]

    project, problems = validate_input(changed)

    assert project is not None
    assert any(
        p["where"] == "P0\u2013P1" and p["blocks_length"]
        and "\u043d\u0443\u043b\u044e" in p["message"]
        for p in problems
    )


def test_route_can_return_to_non_neighboring_point(route_data):
    changed = copy.deepcopy(route_data)
    start = find_point(changed, "P0")
    end = find_point(changed, "P2")
    end["x"], end["y"] = start["x"], start["y"]
    changed["bends"] = []  # \u043f\u0440\u043e\u0432\u0435\u0440\u044f\u0435\u043c \u0442\u043e\u043b\u044c\u043a\u043e \u0442\u043e\u0447\u043a\u0438; \u043e\u0442\u0432\u043e\u0434\u044b \u043a \u043d\u043e\u0432\u043e\u0439 \u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u0438 \u043d\u0435 \u043e\u0442\u043d\u043e\u0441\u044f\u0442\u0441\u044f

    project, problems = validate_input(changed)

    assert project is not None
    assert problems == []


def test_bend_angle_differs_from_route_geometry(route_data):
    changed = copy.deepcopy(route_data)
    changed["bends"][0]["angle_deg"] = 45

    project, problems = validate_input(changed)

    bend_point = changed["bends"][0]["at"]
    assert any(
        p["where"] == bend_point and p["blocks_quantities"]
        and "45" in p["message"] and "90.0" in p["message"]
        for p in problems
    )


def test_bend_at_route_end(route_data):
    changed = copy.deepcopy(route_data)
    changed["bends"][0]["at"] = changed["points"][0]["id"]

    project, problems = validate_input(changed)

    assert any("\u043a\u043e\u043d\u0446\u0435\u0432\u043e\u0439" in p["message"] and p["blocks_quantities"] for p in problems)
