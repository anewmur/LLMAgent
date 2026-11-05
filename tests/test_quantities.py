import json

import pytest

from core.calculations import INPUT_PATH, calculate_route_length, calculate_material_quantities


@pytest.fixture
def data():
    return json.loads(INPUT_PATH.read_text(encoding="utf-8"))


def calculate(data, tmp_path):
    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")
    return calculate_material_quantities(input_file)


@pytest.mark.parametrize("p5_x, expected_length", [(280, 360), (300, 380)])
def test_quantities_follow_route_length(data, tmp_path, p5_x, expected_length):
    data["points"][-1]["x"] = p5_x

    quantities = calculate(data, tmp_path)

    assert quantities["status"] == "ok"
    assert quantities["pipe"] == {
        "material": "ПЭ 100", "sdr": 17,
        "outer_diameter_mm": 110, "wall_mm": 6.6,
        "quantity_m": pytest.approx(expected_length),
    }
    assert quantities["pipe"]["quantity_m"] == calculate_route_length(tmp_path / "route.json")["length_m"]
    assert quantities["bends"] == [{"angle_deg": 90, "quantity_pcs": 2}]


def test_quantities_group_bends_by_angle(data, tmp_path):
    data["bends"][0]["angle_deg"] = 45

    quantities = calculate(data, tmp_path)

    assert quantities["bends"] == [
        {"angle_deg": 45, "quantity_pcs": 1},
        {"angle_deg": 90, "quantity_pcs": 1},
    ]


def test_no_bends_gives_empty_quantity_list(data, tmp_path):
    data["bends"] = []

    quantities = calculate(data, tmp_path)

    assert quantities["status"] == "ok"
    assert quantities["bends"] == []


@pytest.mark.parametrize("issue", ["material", "missing_point", "duplicate_bend"])
def test_quantity_problems_do_not_block_length(data, tmp_path, issue):
    if issue == "material":
        data["pipe"]["material"] = "ПЭ 80"
    elif issue == "missing_point":
        data["bends"][0]["at"] = "P9"
    else:
        data["bends"].append(dict(data["bends"][0]))

    quantities = calculate(data, tmp_path)
    result = calculate_route_length(tmp_path / "route.json")

    assert result["status"] == "ok"
    assert result["length_m"] == pytest.approx(360)
    assert quantities["status"] == "error"
    assert "pipe" not in quantities
    assert "bends" not in quantities
    assert quantities["problems"]
    assert all(p["blocks_quantities"] for p in quantities["problems"])


def test_missing_axis_does_not_block_quantities(data, tmp_path):
    data["points"][3].pop("axis")

    result = calculate(data, tmp_path)

    assert result["status"] == "ok"
    assert result["pipe"]["quantity_m"] == pytest.approx(360)
    assert result["problems"]


@pytest.mark.parametrize("angle", [0, -45, 181, "NaN"])
def test_invalid_bend_angle_is_rejected(data, tmp_path, angle):
    data["bends"][0]["angle_deg"] = angle

    result = calculate(data, tmp_path)

    assert result["status"] == "error"
    assert any("angle_deg" in p["where"] for p in result["problems"])
