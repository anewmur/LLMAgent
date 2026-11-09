from xml.etree import ElementTree as ET

import pytest

from core.documents import DocumentSet
from config.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.formatting import format_pipe_value
from core.models import DocumentId
from core.profile import ProfileDrawing
from core.profile_style import ProfileStyle
from core.session import RouteSession
from core.validate import validate_input


NS = {"s": "http://www.w3.org/2000/svg"}


def test_profile_geometry_scales_and_pipe_contours(route_data, config):
    for p5_x, diameter, wall, length, origin_x in [
        (280, 110, 6.6, 360, 163.0), (300, 160, 9.5, 380, 158.0), (280, 250, 14.8, 360, 163.0),
    ]:
        route_data["points"][-1]["x"] = p5_x
        route_data["pipe"].update(outer_diameter_mm=diameter, wall_mm=wall)
        route_data["object"]["project_code"] = "OTHER-78"
        project, problems = validate_input(route_data)
        assert not problems
        root = ET.fromstring(ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config).render())
        geometry = root.find("s:g[@id='profile-geometry']", NS)
        assert geometry.get("data-horizontal-scale") == "2000"
        assert geometry.get("data-vertical-scale") == "100"
        ground = geometry.find("s:path[@id='ground-line']", NS)
        pipe = geometry.find("s:path[@id='pipe-bottom-line']", NS)
        ground_xy = [tuple(map(float, pair.split(","))) for pair in ground.get("d").split()[1::2]]
        pipe_xy = [tuple(map(float, pair.split(","))) for pair in pipe.get("d").split()[1::2]]
        expected_x = [origin_x + station / 2 for station in [0, 60, 120, 200, 280, length]]
        assert [point_x for point_x, point_y in ground_xy] == pytest.approx(expected_x)
        assert [point_x for point_x, point_y in pipe_xy] == pytest.approx(expected_x)
        assert pipe_xy[-1][0] - pipe_xy[0][0] == pytest.approx(length / 2)
        assert all(30 <= point_x <= 405 for point_x, point_y in ground_xy + pipe_xy)
        all_y = [point_y for point_x, point_y in ground_xy + pipe_xy]
        assert max(point_y for point_x, point_y in pipe_xy) == pytest.approx(76)
        assert min(all_y) > 20
        assert [point_y - ground_xy[0][1] for point_x, point_y in ground_xy] == pytest.approx([0, -4, -6, -10, -14, -16])
        assert [point_y - pipe_xy[0][1] for point_x, point_y in pipe_xy] == pytest.approx([0, -2, -4, -6, -8, -10])
        datum = float(geometry.get("data-datum-m"))
        assert 81 - (102.4 - datum) * 10 == pytest.approx(ground_xy[0][1])
        assert 81 - (100 - diameter / 2000 - datum) * 10 == pytest.approx(pipe_xy[0][1])
        top = geometry.find("s:path[@id='pipe-top-line']", NS)
        assert (top is not None) == (diameter >= 200)
        if top is not None:
            top_xy = [tuple(map(float, pair.split(","))) for pair in top.get("d").split()[1::2]]
            assert [bottom_point[1] - top_point[1] for bottom_point, top_point in zip(pipe_xy, top_xy)] == pytest.approx([2.5] * 6)
        assert pipe.get("stroke-width") == "1.0"
        assert ground.get("stroke-width") == "0.45"
        text = " ".join(root.itertext())
        assert all(value in text for value in ["OTHER-78-НВ", "1:2000", "1:100", "Без изоляции"])
        assert f"Труба полиэтиленовая ПЭ 100 SDR 17 ⌀{diameter}×{format_pipe_value(wall)}" in text
        level = root.find(".//s:text[@data-kind='bottom-level']", NS)
        assert level.get("transform") == "translate(74.5 7.5) rotate(-90)"


def test_profile_slope_cells_show_direction_and_values(route_data, config):
    for point, axis in zip(route_data["points"], [100, 102, 101, 101, 100.8, 101]):
        point["axis"] = axis
    project, problems = validate_input(route_data)
    assert not problems
    root = ET.fromstring(ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config).render())
    lines = root.findall(".//s:path[@data-kind='slope-line']", NS)
    assert len(lines) == 5
    dividers = root.findall(".//s:line[@data-kind='slope-divider']", NS)
    assert [tuple(float(element.get(key)) for key in ["x1", "x2", "y1", "y2"]) for element in dividers] == [
        (106, 106, 77, 99), (136, 136, 77, 99), (176, 176, 77, 99), (216, 216, 77, 99),
    ]
    # В SVG координата Y растёт вниз. Первый участок поднимается на 2 м:
    # направление диагонали не должно зависеть от величины перепада.
    for index, (start_y, end_y, slope, length) in enumerate([
        (99, 77, "33,3", "60,00"),
        (77, 99, "16,7", "60,00"),
        (88, 88, "0", "80,00"),
    ]):
        start, end = [tuple(map(float, pair.split(","))) for pair in lines[index].get("d").split()[1::2]]
        assert start[0] < end[0]
        assert (start[1], end[1]) == (start_y, end_y)
        above = root.find(f".//s:text[@data-kind='slope'][@data-start-id='P{index}']", NS)
        below = root.find(f".//s:text[@data-kind='slope-length'][@data-start-id='P{index}']", NS)
        assert (above.text, below.text) == (slope, length)
        assert float(above.get("y")) < (start_y + end_y) / 2 < float(below.get("y"))


@pytest.mark.parametrize("case", ["missing", "no_levels", "too_long", "too_high", "zero_length"])
def test_profile_missing_levels_and_invalid_geometry(route_data, case, config):
    if case == "missing":
        route_data["points"][2]["axis"] = None
        route_data["points"][4]["ground"] = None
    elif case == "no_levels":
        for point in route_data["points"]:
            point.update(axis=None, ground=None)
    elif case == "too_long":
        route_data["points"][-1]["x"] = 5000
    elif case == "too_high":
        route_data["points"][-1]["ground"] = 120
    else:
        route_data["points"][1]["x"] = 0
    project, problems = validate_input(route_data)
    if case == "zero_length":
        assert any(problem.blocks_length for problem in problems)
        return
    if case == "too_high":
        assert ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config).render()
        return
    if case != "missing":
        with pytest.raises(ValueError):
            ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config).render()
        return
    assert {problem.where for problem in problems} == {"P2", "P4"}
    root = ET.fromstring(ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config).render())
    ground = root.find(".//s:path[@id='ground-line']", NS).get("d").split()
    pipe = root.find(".//s:path[@id='pipe-bottom-line']", NS).get("d").split()
    assert ground[::2] == ["M", "L", "L", "L", "M"]
    assert pipe[::2] == ["M", "L", "M", "L", "L"]
    pipe_x = [float(pair.split(",")[0]) for pair in pipe[1::2]]
    assert [point_x - pipe_x[0] for point_x in pipe_x] == pytest.approx([0, 30, 100, 140, 180])


def test_font_steps_and_title_size():
    assert ProfileStyle.font_step(DEFAULT_FONT_SIZE_MM, 1) == 5
    assert ProfileStyle.font_step(DEFAULT_FONT_SIZE_MM, -1) == 2.5
    assert ProfileStyle.font_step(2.5, -1) == 2.5
    assert ProfileStyle.font_step(14, 1) == 14
    assert [ProfileStyle(size).title_size for size in [2.5, DEFAULT_FONT_SIZE_MM, 5]] == [5, 7, 10]
    with pytest.raises(ValueError):
        ProfileStyle(3.7)


def test_font_tool_reissues_sheet_and_preserves_it_when_size_does_not_fit(input_file, tmp_path, config):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    for direction, size in [(-1, 2.5), (1, DEFAULT_FONT_SIZE_MM)]:
        result = session.change_profile_font(direction)
        assert result["status"] == "ok", result
        assert session.font_size == size
        assert (folder / "pdf/package.pdf").exists()
        if size == 2.5:
            before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
            assert session.change_profile_font(-1) == {"status": "ok", "message": "Значения не изменились."}
            assert session.font_size == 2.5 and len(session.changes) == 1
            assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
        geometry = ET.parse(folder / "profile.svg").getroot().find("s:g[@id='profile-geometry']", NS)
        assert float(geometry.get("data-font-size")) == size
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    assert session.change_profile_font(1)["status"] == "error"
    assert session.font_size == DEFAULT_FONT_SIZE_MM and len(session.changes) == 2
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
