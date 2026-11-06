import json

import pytest

from core.calculations import calculate_pipe_levels
from core.validate import validate_input


@pytest.mark.parametrize(
    "diameter_mm, expected_bottom, expected_depth",
    [(110, 99.945, 2.455), (200, 99.9, 2.5)],
)
def test_route_point_levels(route_data, tmp_path, diameter_mm, expected_bottom, expected_depth):
    route_data["pipe"]["outer_diameter_mm"] = diameter_mm
    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(route_data), encoding="utf-8")

    result = calculate_pipe_levels(input_file)

    assert result["status"] == "ok"
    assert [p["point_id"] for p in result["point_levels"]] == [
        "P0", "P1", "P2", "P3", "P4", "P5",
    ]
    first = result["point_levels"][0]
    assert first["bottom_m"] == pytest.approx(expected_bottom)
    assert first["depth_to_bottom_m"] == pytest.approx(expected_depth)


@pytest.mark.parametrize("missing_fields", [("axis",), ("ground",), ("axis", "ground")])
def test_missing_levels_keep_available_calculations(route_data, tmp_path, missing_fields):
    for point in route_data["points"]:
        if point["id"] == "P3":
            for field in missing_fields:
                point.pop(field, None)
    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(route_data), encoding="utf-8")

    result = calculate_pipe_levels(input_file)

    assert result["status"] == "ok"
    p3 = next(p for p in result["point_levels"] if p["point_id"] == "P3")
    if "axis" in missing_fields:
        assert p3["bottom_m"] is None
    else:
        assert p3["bottom_m"] == pytest.approx(100.545)
    assert p3["depth_to_bottom_m"] is None
    assert result["point_levels"][0]["depth_to_bottom_m"] == pytest.approx(2.455)
    for field in missing_fields:
        assert any(
            p["where"] == "P3" and field in p["message"]
            for p in result["problems"]
        )


@pytest.mark.parametrize("field", ["axis", "ground", "outer_diameter_mm"])
@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_level_inputs_are_rejected(route_data, field, value):
    if field == "outer_diameter_mm":
        route_data["pipe"][field] = value
    else:
        route_data["points"][0][field] = value

    project, problems = validate_input(route_data)

    assert project is None
    assert any(field in p["where"] for p in problems)


@pytest.mark.parametrize("diameter_mm", [0, -110])
def test_nonpositive_diameter_is_rejected(route_data, diameter_mm):
    route_data["pipe"]["outer_diameter_mm"] = diameter_mm

    project, problems = validate_input(route_data)

    assert project is None
    assert any("outer_diameter_mm" in p["where"] for p in problems)
