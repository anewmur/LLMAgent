import json
from xml.etree import ElementTree as ET

import pytest

from core.profile import ProfileExport, create_profile
from core.profile_style import ProfileStyle


NS = {"s": "http://www.w3.org/2000/svg"}


def test_profile_geometry_scales_and_pipe_contours(route_data, tmp_path):
    for p5_x, diameter, length, origin_x in [
        (280, 110, 360, 164.5), (300, 160, 380, 159.5), (280, 250, 360, 164.5),
    ]:
        route_data["points"][-1]["x"] = p5_x
        route_data["pipe"]["outer_diameter_mm"] = diameter
        route_data["object"]["project_code"] = "OTHER-78"
        input_file = tmp_path / "route.json"
        input_file.write_text(json.dumps(route_data), encoding="utf-8")
        output = tmp_path / "profile.svg"
        assert create_profile(input_file, output)["status"] == "ok"
        root = ET.parse(output).getroot()
        assert root.attrib == {"width": "420mm", "height": "297mm", "viewBox": "0 0 420 297"}
        frame = root.find("s:g/s:rect[@id='frame']", NS)
        assert (frame.get("width"), frame.get("height")) == ("395", "287")
        stamp = root.find("s:g/s:rect[@id='title-block']", NS)
        assert (stamp.get("x"), stamp.get("y"), stamp.get("width"), stamp.get("height")) == (
            "230", "237", "185", "55",
        )
        geometry = root.find("s:g[@id='profile-geometry']", NS)
        assert geometry.get("data-horizontal-scale") == "2000"
        assert geometry.get("data-vertical-scale") == "100"
        ground = geometry.find("s:path[@id='ground-line']", NS)
        pipe = geometry.find("s:path[@id='pipe-bottom-line']", NS)
        ground_xy = [tuple(map(float, xy.split(","))) for xy in ground.get("d").split()[1::2]]
        pipe_xy = [tuple(map(float, xy.split(","))) for xy in pipe.get("d").split()[1::2]]
        expected_x = [origin_x + s / 2 for s in [0, 60, 120, 200, 280, length]]
        assert [x for x, y in ground_xy] == pytest.approx(expected_x)
        assert [x for x, y in pipe_xy] == pytest.approx(expected_x)
        assert pipe_xy[-1][0] - pipe_xy[0][0] == pytest.approx(length / 2)
        assert all(30 <= x <= 405 for x, y in ground_xy + pipe_xy)
        all_y = [y for x, y in ground_xy + pipe_xy]
        assert (min(all_y) + max(all_y)) / 2 == pytest.approx(43)
        assert min(all_y) >= 15 and max(all_y) <= 71
        assert [y - ground_xy[0][1] for x, y in ground_xy] == pytest.approx([0, -4, -6, -10, -14, -16])
        assert [y - pipe_xy[0][1] for x, y in pipe_xy] == pytest.approx([0, -2, -4, -6, -8, -10])
        datum = float(geometry.get("data-datum-m"))
        assert 81 - (102.4 - datum) * 10 == pytest.approx(ground_xy[0][1])
        assert 81 - (100 - diameter / 2000 - datum) * 10 == pytest.approx(pipe_xy[0][1])
        top = geometry.find("s:path[@id='pipe-top-line']", NS)
        assert (top is not None) == (diameter >= 200)
        if top is not None:
            top_xy = [tuple(map(float, xy.split(","))) for xy in top.get("d").split()[1::2]]
            assert [a[1] - b[1] for a, b in zip(pipe_xy, top_xy)] == pytest.approx([2.5] * 6)
        assert pipe.get("stroke-width") == "1.0"
        assert ground.get("stroke-width") == "0.45"
        text = " ".join(root.itertext())
        assert all(value in text for value in ["OTHER-78-НВ", "1:2000", "1:100", "УЧЕБНЫЙ КОМПЛЕКТ", "Без изоляции"])
        level = root.find(".//s:text[@data-kind='bottom-level']", NS)
        assert level.get("transform") == "translate(74.5 7.5) rotate(-90)"


def test_profile_slope_cells_show_direction_and_values(route_data, tmp_path):
    for point, axis in zip(route_data["points"], [100, 102, 101, 101, 100.8, 101]):
        point["axis"] = axis
    source, output = tmp_path / "route.json", tmp_path / "profile.svg"
    source.write_text(json.dumps(route_data), encoding="utf-8")
    assert create_profile(source, output)["status"] == "ok"
    root = ET.parse(output).getroot()
    lines = root.findall(".//s:path[@data-kind='slope-line']", NS)
    assert len(lines) == 5
    dividers = root.findall(".//s:line[@data-kind='slope-divider']", NS)
    assert [tuple(float(e.get(k)) for k in ["x1", "x2", "y1", "y2"]) for e in dividers] == [
        (106, 106, 77, 99), (136, 136, 77, 99), (176, 176, 77, 99), (216, 216, 77, 99),
    ]
    # В SVG координата Y растёт вниз. Первый участок поднимается на 2 м:
    # направление диагонали не должно зависеть от величины перепада.
    for i, (start_y, end_y, slope, length) in enumerate([
        (99, 77, "33,33", "60,00"),
        (77, 99, "-16,67", "60,00"),
        (88, 88, "0,00", "80,00"),
    ]):
        start, end = [tuple(map(float, xy.split(","))) for xy in lines[i].get("d").split()[1::2]]
        assert start[0] < end[0]
        assert (start[1], end[1]) == (start_y, end_y)
        above = root.find(f".//s:text[@data-kind='slope'][@data-start-id='P{i}']", NS)
        below = root.find(f".//s:text[@data-kind='slope-length'][@data-start-id='P{i}']", NS)
        assert (above.text, below.text) == (slope, length)
        assert float(above.get("y")) < (start_y + end_y) / 2 < float(below.get("y"))


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
    assert [x - pipe_x[0] for x in pipe_x] == pytest.approx([0, 30, 100, 140, 180])


def test_font_steps_and_title_size():
    assert ProfileStyle.font_step(3.5, 1) == 5
    assert ProfileStyle.font_step(3.5, -1) == 2.5
    assert ProfileStyle.font_step(2.5, -1) == 2.5
    assert ProfileStyle.font_step(14, 1) == 14
    assert [ProfileStyle(s).title_size for s in [2.5, 3.5, 5]] == [5, 7, 10]
    with pytest.raises(ValueError):
        ProfileStyle(3.7)


def test_font_tool_reissues_sheet_and_preserves_it_when_size_does_not_fit(input_file, tmp_path):
    exporter = ProfileExport(input_file, tmp_path / "profile.svg")
    assert exporter.create()["status"] == "ok"
    for direction, size in [(-1, 2.5), (1, 3.5)]:
        result = exporter.change_font(direction)
        assert result["status"] == "ok", result
        assert result["base_font_size"] == size
        assert (tmp_path / "profile.pdf").exists()
    previous = (tmp_path / "profile.svg").read_bytes()
    assert exporter.change_font(1)["status"] == "error"
    assert (tmp_path / "profile.svg").read_bytes() == previous
