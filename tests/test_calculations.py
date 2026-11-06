import json

import pytest
from core.calculations import calculate_slope
from core.calculations import calculate_route_length, calculate_route_geometry
from core.models import Point


@pytest.mark.parametrize("string_coordinates", [False, True])
def test_route_length_uses_validated_coordinates(route_data, tmp_path, string_coordinates):
    data = route_data
    if string_coordinates:
        for point in data["points"]:
            point["x"] = str(point["x"])
            point["y"] = str(point["y"])

    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = calculate_route_length(input_file)

    assert result["status"] == "ok"
    assert result["length_m"] == pytest.approx(360.0)
    assert result["problems"] == []


@pytest.mark.parametrize(
    "p5_x, expected_lengths, expected_cumsum_distances",
    [
        (280, [60, 60, 80, 80, 80], [60, 120, 200, 280, 360]),
        (300, [60, 60, 80, 80, 100], [60, 120, 200, 280, 380]),
    ],
)
def test_sections_and_cumsum_distances(
    route_data, tmp_path, p5_x, expected_lengths, expected_cumsum_distances
):
    data = route_data

    for point in data["points"]:
        if point["id"] == "P5":
            point["x"] = p5_x

    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = calculate_route_length(input_file)

    assert result["status"] == "ok"

    sections = result["sections"]

    assert [
        (section["start_id"], section["end_id"])
        for section in sections
    ] == [
        ("P0", "P1"),
        ("P1", "P2"),
        ("P2", "P3"),
        ("P3", "P4"),
        ("P4", "P5"),
    ]

    assert [
        section["length_m"] for section in sections
    ] == pytest.approx(expected_lengths)

    assert [
        section["cumsum_dist_m"] for section in sections
    ] == pytest.approx(expected_cumsum_distances)

    assert [
        section["start_station_m"] for section in sections
    ] == pytest.approx([0, 60, 120, 200, 280])
    assert sections[0]["start_id"] == "P0"
    assert sections[0]["start_station_m"] == 0.0
    p3_section = next(s for s in sections if s["start_id"] == "P3")
    assert p3_section["start_station_m"] == 200.0  # \u041f\u041a 2+00

    assert result["length_m"] == pytest.approx(
        sum(expected_lengths)
    )

    assert [
        section["slope_per_mille"] for section in sections
    ] == pytest.approx([
        10 / 3, 10 / 3, 2.5, 2.5, 0.2 / (p5_x - 200) * 1000,
    ])


def test_missing_axis_affects_only_neighboring_slopes(route_data, tmp_path):
    data = route_data
    for point in data["points"]:
        if point["id"] == "P3":
            point.pop("axis", None)
    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = calculate_route_length(input_file)

    assert result["status"] == "ok"
    assert result["length_m"] == pytest.approx(360.0)
    sections = result["sections"]
    assert sections[2]["slope_per_mille"] is None  # P2\u2013P3
    assert sections[3]["slope_per_mille"] is None  # P3\u2014P4
    assert [
        sections[i]["slope_per_mille"] for i in (0, 1, 4)
    ] == pytest.approx([10 / 3, 10 / 3, 2.5])
    assert any(
        p["where"] == "P3" and "axis" in p["message"]
        for p in result["problems"]
    )


def test_geometry_preserves_unrounded_lengths_and_stations():
    points = [
        Point(id="P0", x=0, y=0),
        Point(id="P1", x=1, y=1),
        Point(id="P2", x=2, y=0),
    ]

    result = calculate_route_geometry(points)

    first, second = result["sections"]
    assert first["length_m"] == 2 ** 0.5
    assert first["length_m"] != round(first["length_m"], 2)
    assert first["start_station_m"] == 0.0
    assert second["start_station_m"] == first["cumsum_dist_m"] == 2 ** 0.5
    assert result["length_m"] == second["cumsum_dist_m"] == 2 * 2 ** 0.5
    assert set(result) == {"length_m", "sections"}


@pytest.mark.parametrize(
    "start_axis, end_axis, expected",
    [
        (100.0, 100.2, 10 / 3),
        (100.2, 100.0, -10 / 3),
        (100.0, 100.0, 0.0),
        (None, 100.2, None),
        (100.0, None, None),
    ],
)
def test_slope(start_axis, end_axis, expected):
    start = Point(id="P0", x=0, y=0, axis=start_axis)
    end = Point(id="P1", x=60, y=0, axis=end_axis)

    result = calculate_slope(start, end, length_m=60)

    if expected is None:
        assert result is None
    else:
        assert result == pytest.approx(expected)


@pytest.mark.parametrize("length_m", [0, -1])
def test_slope_unavailable_for_nonpositive_length(length_m):
    start = Point(id="P0", x=0, y=0, axis=100.0)
    end = Point(id="P1", x=0, y=0, axis=100.2)

    assert calculate_slope(start, end, length_m=length_m) is None


def test_zero_length_section_blocks_route_calculation(route_data, tmp_path):
    data = route_data
    data["points"][1]["x"] = data["points"][0]["x"]
    data["points"][1]["y"] = data["points"][0]["y"]
    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = calculate_route_length(input_file)

    assert result["status"] == "error"
    assert "length_m" not in result
    assert any(
        p["where"] == "P0\u2013P1" and p["blocks_length"]
        and "\u043d\u0443\u043b\u044e" in p["message"]
        for p in result["problems"]
    )
