import re
from xml.etree import ElementTree as ET

import pytest

from core import drawing_settings as settings
from core.assumptions import load_assumptions
from core.documents import DocumentSet
from core.models import DocumentId, Project, Status
from core.pipe_drawing import pipe_leader, pipe_line_count
from core.pipe_geometry import PipeContours
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.release import create_package


NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.mark.parametrize("diameter, scale, expected", [(110, 1000, 1), (1999, 1000, 1),
                                                       (2000, 1000, 2), (2200, 1000, 2), (250, 100, 2)])
def test_pipe_line_count_at_threshold(diameter, scale, expected):
    assert pipe_line_count(diameter, scale) == expected


@pytest.mark.parametrize("end_y, sweep", [(20, 1), (-20, 0)])
def test_contours_have_concentric_tangent_arcs(end_y, sweep):
    geometry = PipeContours([(0, 0), (20, 0), (20, end_y)], {1}, 2.2)
    assert geometry.radius == pytest.approx(3.3)
    assert geometry.corners[0].tangent == pytest.approx(3.3)
    for offset in (-1.1, 0, 1.1):
        path = geometry.path_data(offset)
        arc = re.search(r"A ([\d.e+-]+),([\d.e+-]+) 0 0 ([01])", path)
        expected_radius = 3.3 - offset * (1 if sweep else -1)
        assert float(arc.group(1)) == pytest.approx(expected_radius)
        assert float(arc.group(2)) == pytest.approx(expected_radius)
        assert int(arc.group(3)) == sweep
        entry = path.split(" L ", 1)[1].split(" A ", 1)[0]
        assert tuple(map(float, entry.split(","))) == pytest.approx((16.7, offset))
    assert " A " not in PipeContours([(0, 0), (20, 0), (20, end_y)], set(), 2.2).path_data(1.1)


def test_plan_contours_and_optional_axis(route_data, config, monkeypatch):
    route_data["pipe"].update(outer_diameter_mm=2200, wall_mm=130)
    project = Project.model_validate(route_data)
    document = DocumentSet(project, config).get(DocumentId.PLAN)
    root = ET.fromstring(PlanDrawing(project, document).render())
    contours = root.findall(".//s:g[@id='pipe-contours']/s:path", NS)
    assert len(contours) == 2 and all(" A " in path.get("d") for path in contours)
    axis = root.find(".//s:path[@id='route-axis']", NS)
    assert axis is not None and axis.get("stroke-dasharray") == settings.PIPE_AXIS_DASHARRAY_MM
    assert float(axis.get("stroke-width")) < settings.PLAN_ROUTE_LINE_WIDTH_MM / 2
    assert root.find(".//s:polyline[@id='route-line']", NS).get("visibility") == "hidden"
    monkeypatch.setattr(settings, "DRAW_PIPE_AXIS", False)
    assert ET.fromstring(PlanDrawing(project, document).render()).find(".//s:path[@id='route-axis']", NS) is None
    project.bends = []
    root = ET.fromstring(PlanDrawing(project, document).render())
    assert all(" A " not in path.get("d") for path in root.findall(".//s:g[@id='pipe-contours']/s:path", NS))


def test_shared_pipe_leader_and_profile_have_correct_text(route_data, config):
    project = Project.model_validate(route_data)
    label = ET.fromstring(pipe_leader(project.pipe, (10, 20), (20, 10)))
    texts = label.findall("text")
    assert [element.text for element in texts] == ["В1", "⌀110×6,6"]
    assert "ПЭ 100" not in "".join(label.itertext()) and "SDR" not in "".join(label.itertext())
    assert float(texts[0].get("y")) < 10 < float(texts[1].get("y"))
    assert " H " in label.find("path").get("d")
    project.pipe.outer_diameter_mm, project.pipe.wall_mm = 250, 14.8
    root = ET.fromstring(ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config).render())
    assert root.find(".//s:g[@data-kind='pipe-label']/s:text[@data-kind='pipe-size']", NS).text == "⌀250×14,8"
    assert " A " not in root.find(".//s:path[@id='pipe-bottom-line']", NS).get("d")


def test_crowded_bend_warns_and_package_is_published(route_data, config, tmp_path):
    route_data["pipe"].update(outer_diameter_mm=2200, wall_mm=130)
    route_data["points"][1]["x"] = 119
    project = Project.model_validate(route_data)
    result = create_package(project, tmp_path / "package", config)
    assert result["status"] == Status.WARNING, result
    warning = next(check for check in result["checks"] if check.name == "plan_bends" and check.status == Status.WARNING)
    assert "P2" in warning.message and "3,30" in warning.message and "0,50" in warning.message
    report = (tmp_path / "package/check_report.md").read_text(encoding="utf-8")
    assert "пп. 3.5, 3.7" in report and "пп. 3.8, 3.9, 3.11" in report
    assert "табл. 1, п. 8в" in report
    items = load_assumptions(config, project, 100)
    assert all(item.full in report for item in items)
    assert any("Радиус отвода принят равным 1,5" in item.full for item in items)
    assert (tmp_path / "package/pdf/package.pdf").is_file()


@pytest.mark.parametrize("diameter, wall", [(110, 6.6), (2200, 130)])
def test_bend_marker_is_mid_arc_or_vertex(route_data, config, diameter, wall):
    from math import sqrt
    route_data["pipe"].update(outer_diameter_mm=diameter, wall_mm=wall)
    project = Project.model_validate(route_data)
    drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN))
    root = ET.fromstring(drawing.render())
    circles = root.findall(".//s:circle[@data-point-id]", NS)
    marker = circles[2]
    actual = float(marker.get("cx")), float(marker.get("cy"))
    vertex_x, vertex_y = drawing.coordinates[2]
    offset = 1.5 * diameter / drawing.scale * (1 - 1 / sqrt(2)) if diameter == 2200 else 0
    assert actual == pytest.approx((vertex_x - offset, vertex_y - offset), abs=0.01)
    axis = root.find(".//s:path[@id='route-axis']", NS)
    if axis is not None:
        assert axis.get("d").count("M ") == 1
    assert "X=120,00, Y=0,00" in "".join(root.itertext())
