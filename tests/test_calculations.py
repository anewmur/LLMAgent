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
