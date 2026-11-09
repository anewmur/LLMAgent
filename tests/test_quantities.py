import pytest

from core.session import RouteSession
from core.validate import validate_input


def calculate(data, tmp_path, config, write_route):
    input_file = write_route(data, "route.json")
    return RouteSession(input_file, tmp_path / "output", config).calculate_material_quantities()


@pytest.mark.parametrize("p5_x, expected_length", [(280, 360), (300, 380)])
def test_quantities_follow_route_length(route_data, tmp_path, p5_x, expected_length, config, write_route):
    route_data["points"][-1]["x"] = p5_x

    quantities = calculate(route_data, tmp_path, config, write_route)

    assert quantities["status"] == "ok"
    assert quantities["pipe"] == {
        "material": "\u041f\u042d 100", "sdr": 17,
        "outer_diameter_mm": 110, "wall_mm": 6.6,
        "standard": None,
        "quantity_m": pytest.approx(expected_length),
    }
    assert quantities["bends"] == [{"angle_deg": 90, "quantity_pcs": 2}]


def test_bend_angle_not_matching_route_blocks_quantities(route_data, tmp_path, config, write_route):
    # \u0422\u0440\u0430\u0441\u0441\u0430 \u043f\u043e\u0432\u043e\u0440\u0430\u0447\u0438\u0432\u0430\u0435\u0442 \u043d\u0430 90, \u0430 \u0432 \u0434\u0430\u043d\u043d\u044b\u0445 \u043e\u0442\u0432\u043e\u0434 45 \u2014 \u0441\u043f\u0435\u0446\u0438\u0444\u0438\u043a\u0430\u0446\u0438\u044e \u0432\u044b\u043f\u0443\u0441\u043a\u0430\u0442\u044c \u043d\u0435\u043b\u044c\u0437\u044f.
    route_data["bends"][0]["angle_deg"] = 45

    quantities = calculate(route_data, tmp_path, config, write_route)

    assert quantities["status"] == "error"
    assert "bends" not in quantities
    assert any(problem["where"] == route_data["bends"][0]["at"] for problem in quantities["problems"])


def test_no_bends_gives_empty_quantity_list(route_data, tmp_path, config, write_route):
    route_data["points"] = route_data["points"][:3]
    route_data["bends"] = []

    quantities = calculate(route_data, tmp_path, config, write_route)

    assert quantities["status"] == "ok"
    assert quantities["bends"] == []


@pytest.mark.parametrize("issue", ["material", "missing_point", "duplicate_bend"])
def test_quantity_problems_do_not_block_length(route_data, tmp_path, issue, config, write_route):
    if issue == "material":
        route_data["pipe"]["material"] = "\u041f\u042d 80"
    elif issue == "missing_point":
        route_data["bends"][0]["at"] = "P9"
    else:
        route_data["bends"].append(dict(route_data["bends"][0]))

    quantities = calculate(route_data, tmp_path, config, write_route)
    result = RouteSession(tmp_path / "route.json", tmp_path / "output", config).calculate_route_length()

    assert result["status"] == "ok"
    assert result["length_m"] == pytest.approx(360)
    assert quantities["status"] == "error"
    assert "pipe" not in quantities
    assert "bends" not in quantities
    assert quantities["problems"]
    assert all(problem["blocks_quantities"] for problem in quantities["problems"])


def test_missing_axis_does_not_block_quantities(route_data, tmp_path, config, write_route):
    route_data["points"][3].pop("axis")

    result = calculate(route_data, tmp_path, config, write_route)

    assert result["status"] == "ok"
    assert result["pipe"]["quantity_m"] == pytest.approx(360)
    assert result["problems"]


@pytest.mark.parametrize("angle", [0, -45, 181, "NaN"])
def test_invalid_bend_angle_is_rejected(route_data, angle):
    route_data["bends"][0]["angle_deg"] = angle

    project, problems = validate_input(route_data)
    assert project is None
    assert any("angle_deg" in problem.where for problem in problems)
