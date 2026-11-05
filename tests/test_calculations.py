import json

import pytest

from core.calculations import INPUT_PATH, calculate_route_length


@pytest.mark.parametrize("string_coordinates", [False, True])
def test_route_length_uses_validated_coordinates(tmp_path, string_coordinates):
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    if string_coordinates:
        for point in data["points"]:
            point["x"] = str(point["x"])
            point["y"] = str(point["y"])

    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")

    result = calculate_route_length(input_file)

    assert result["status"] == "ok"
    assert result["length_m"] == pytest.approx(360.0)
    assert result["problems_for_later"] == []


@pytest.mark.parametrize(
    "p5_x, expected_lengths, expected_cumsum_distances",
    [
        (280, [60, 60, 80, 80, 80], [60, 120, 200, 280, 360]),
        (300, [60, 60, 80, 80, 100], [60, 120, 200, 280, 380]),
    ],
)

def test_sections_and_cumsum_distances(
    tmp_path, p5_x, expected_lengths, expected_cumsum_distances
):
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))

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

    assert result["length_m"] == pytest.approx(
        sum(expected_lengths)
    )
