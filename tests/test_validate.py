import copy

import pytest

from core.models import Level, ProblemCode
from core.validate import validate_input


def find_point(data, point_id):
    for point in data["points"]:
        if point["id"] == point_id:
            return point
    raise KeyError(point_id)


def test_original_input_has_no_problems(route_data):
    project, problems = validate_input(route_data)
    assert project is not None
    assert problems == []


def test_missing_axis_p3(route_data):
    changed = copy.deepcopy(route_data)
    del find_point(changed, "P3")["axis"]
    project, problems = validate_input(changed)
    assert any(problem.where == "P3" and "axis" in problem.message for problem in problems)


def test_material_conflict(route_data):
    changed = copy.deepcopy(route_data)
    changed["pipe"]["material"] = "\u041f\u042d 80"
    project, problems = validate_input(changed)
    assert any(problem.where == "pipe" and "\u043c\u0430\u0442\u0435\u0440\u0438\u0430\u043b" in problem.message for problem in problems)


def test_bend_on_missing_point(route_data):
    changed = copy.deepcopy(route_data)
    changed["bends"][0]["at"] = "P9"
    project, problems = validate_input(changed)
    assert any(problem.where == "P9" for problem in problems)


def test_duplicate_point_id(route_data):
    changed = copy.deepcopy(route_data)
    changed["points"][1]["id"] = "P0"
    project, problems = validate_input(changed)
    assert any("\u043f\u043e\u0432\u0442\u043e\u0440\u044f\u0435\u0442\u0441\u044f" in problem.message for problem in problems)


def test_coincident_neighboring_points(route_data):
    changed = copy.deepcopy(route_data)
    start = find_point(changed, "P0")
    end = find_point(changed, "P1")
    end["x"], end["y"] = start["x"], start["y"]

    project, problems = validate_input(changed)

    assert project is not None
    assert any(
        problem.where == "P0\u2013P1" and problem.blocks_length
        and "\u043d\u0443\u043b\u044e" in problem.message
        for problem in problems
    )


def test_route_can_return_to_non_neighboring_point(route_data):
    changed = copy.deepcopy(route_data)
    changed["points"] = changed["points"][:3]
    start = find_point(changed, "P0")
    end = find_point(changed, "P2")
    end["x"], end["y"] = start["x"], start["y"]
    changed["bends"] = [{"at": "P1", "angle_deg": 180}]

    project, problems = validate_input(changed)

    assert project is not None
    assert problems == []


def test_bend_angle_differs_from_route_geometry(route_data):
    changed = copy.deepcopy(route_data)
    changed["bends"][0]["angle_deg"] = 45

    project, problems = validate_input(changed)

    bend_point = changed["bends"][0]["at"]
    assert any(
        problem.where == bend_point and problem.blocks_quantities
        and problem.message == "угол отвода в данных 45, по координатам поворот 90"
        for problem in problems
    )


def test_bend_at_route_end(route_data):
    changed = copy.deepcopy(route_data)
    changed["bends"][0]["at"] = changed["points"][0]["id"]

    project, problems = validate_input(changed)

    assert any("\u043a\u043e\u043d\u0446\u0435\u0432\u043e\u0439" in problem.message and problem.blocks_quantities for problem in problems)


@pytest.mark.parametrize("diameter, wall, sdr, expected_code", [
    (110, 6.6, 17, None),
    (160, 9.5, 17, None),
    (160, 6.6, 17, ProblemCode.PIPE_SDR_MISMATCH),
    (100, 10, 10.5, None),
    (100, 10, 10.5001, ProblemCode.PIPE_SDR_MISMATCH),
    (160, 0, 17, ProblemCode.STRUCTURE),
])
def test_pipe_dimensions_match_sdr_with_tolerance(route_data, diameter, wall, sdr, expected_code):
    route_data["pipe"].update(outer_diameter_mm=diameter, wall_mm=wall, sdr=sdr)

    project, problems = validate_input(route_data)

    if expected_code is None:
        assert project is not None and not problems
    else:
        assert any(problem.code == expected_code and problem.level == Level.ERROR for problem in problems)
        if expected_code == ProblemCode.PIPE_SDR_MISMATCH:
            assert all(problem.where == "pipe" and problem.blocks_quantities for problem in problems)


def test_unbent_turn_uses_actual_angle_and_decimal_comma(route_data):
    from core.formatting import format_number
    from core.validate import InputValidator

    project, problems = validate_input(route_data)
    assert project is not None and not any(problem.code == ProblemCode.MISSING_BEND for problem in problems)
    route_data["points"][-1]["y"] = 120
    validator = InputValidator(route_data)
    project, problems = validator.validate()
    missing = [problem for problem in problems if problem.code == ProblemCode.MISSING_BEND]
    assert len(missing) == 1 and missing[0].where == "P4"
    assert missing[0].level == Level.ERROR and missing[0].blocks_quantities
    assert format_number(validator.turn_angle(4)) == "26,57"
    assert missing[0].message == "поворот трассы 26,57 без отвода"
