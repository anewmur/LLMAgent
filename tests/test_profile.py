import json
from xml.etree import ElementTree as ET

import pytest

from core.profile import create_profile


NS = {"s": "http://www.w3.org/2000/svg"}


def test_profile_geometry_scales_and_a2_sheet(route_data, tmp_path):
    for p5_x, diameter, length, origin_x, bottom_y in [
        (280, 110, 360, 159.5, 190.55), (300, 160, 380, 149.5, 190.8),
    ]:
        route_data["points"][-1]["x"] = p5_x
        route_data["pipe"]["outer_diameter_mm"] = diameter
        route_data["object"]["project_code"] = "OTHER-78"
        input_file = tmp_path / "route.json"
        input_file.write_text(json.dumps(route_data), encoding="utf-8")
        output = tmp_path / "profile.svg"
        assert create_profile(input_file, output)["status"] == "ok"
        root = ET.parse(output).getroot()
        assert root.attrib == {"width": "594mm", "height": "420mm", "viewBox": "0 0 594 420"}
        frame = root.find("s:g/s:rect[@id='frame']", NS)
        assert (frame.get("width"), frame.get("height")) == ("569", "410")
        stamp = root.find("s:g/s:rect[@id='title-block']", NS)
        assert (stamp.get("x"), stamp.get("y"), stamp.get("width"), stamp.get("height")) == (
            "404", "360", "185", "55",
        )
        geometry = root.find("s:g[@id='profile-geometry']", NS)
        assert geometry.get("data-horizontal-scale") == "1000"
        assert geometry.get("data-vertical-scale") == "100"
        assert geometry.get("data-datum-m") == "98"
        ground = geometry.find("s:path[@id='ground-line']", NS)
        pipe = geometry.find("s:path[@id='pipe-bottom-line']", NS)
        ground_xy = [tuple(map(float, xy.split(","))) for xy in ground.get("d").split()[1::2]]
        pipe_xy = [tuple(map(float, xy.split(","))) for xy in pipe.get("d").split()[1::2]]
        expected_x = [origin_x + s for s in [0, 60, 120, 200, 280, length]]
        assert [x for x, y in ground_xy] == pytest.approx(expected_x)
        assert [x for x, y in pipe_xy] == pytest.approx(expected_x)
        assert [y for x, y in ground_xy] == pytest.approx([166, 162, 160, 156, 152, 150])
        assert [y for x, y in pipe_xy] == pytest.approx([bottom_y - 2 * i for i in range(6)])
        text = " ".join(root.itertext())
        assert all(value in text for value in ["OTHER-78-НВ", "1:1000", "1:100", "УЧЕБНЫЙ КОМПЛЕКТ"])


@pytest.mark.parametrize("case", ["missing", "no_levels", "too_long", "too_high", "zero_length"])
def test_profile_missing_levels_and_invalid_geometry(route_data, tmp_path, case):
    if case == "missing":
        route_data["points"][2]["axis"] = None
        route_data["points"][4]["ground"] = None
    elif case == "no_levels":
        for point in route_data["points"]:
            point.update(axis=None, ground=None)
    elif case == "too_long":
        route_data["points"][-1]["x"] = 800
    elif case == "too_high":
        route_data["points"][-1]["ground"] = 120
    else:
        route_data["points"][1]["x"] = 0
    input_file = tmp_path / "route.json"
    input_file.write_text(json.dumps(route_data), encoding="utf-8")
    output = tmp_path / "profile.svg"
    result = create_profile(input_file, output)
    if case != "missing":
        assert result["status"] == "error"
        assert not output.exists()
        return
    assert result["status"] == "ok"
    assert {p["where"] for p in result["problems"]} == {"P2", "P4"}
    root = ET.parse(output).getroot()
    ground = root.find(".//s:path[@id='ground-line']", NS).get("d").split()
    pipe = root.find(".//s:path[@id='pipe-bottom-line']", NS).get("d").split()
    assert ground[::2] == ["M", "L", "L", "L", "M"]
    assert pipe[::2] == ["M", "L", "M", "L", "L"]
    pipe_x = [float(xy.split(",")[0]) for xy in pipe[1::2]]
    assert [x - pipe_x[0] for x in pipe_x] == pytest.approx([0, 60, 200, 280, 360])
