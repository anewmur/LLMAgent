from xml.etree import ElementTree as ET
import pytest

from config import drawing_settings as settings
from core.assumptions import load_assumptions
from core.documents import DocumentSet
from core.models import Project, DocumentId
from core.pipe_drawing import pipe_leader, leader_crosses_shelf_text
from core.plan import PlanDrawing
from core.specification import SpecificationDrawing, HEADERS, WIDTHS
from core.tables import TableCell, text_width

NS = {"s": "http://www.w3.org/2000/svg"}


def test_shared_leader_avoids_its_text_and_detects_bad_segment(route_data):
    pipe = Project.model_validate(route_data).pipe
    for target in ((10, 30), (70, 30)):
        label = ET.fromstring(pipe_leader(pipe, target, (20, 10)))
        assert not leader_crosses_shelf_text(label)
    label.find("path").set("d", "M 37,30 L 37,10 H 72")
    assert leader_crosses_shelf_text(label)


def test_double_plan_contour_clearance_extensions_legend_and_assumptions(route_data, config, monkeypatch):
    route_data["pipe"].update(outer_diameter_mm=2200, wall_mm=130)
    project = Project.model_validate(route_data)
    drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN))
    assert drawing.marker_coordinates != drawing.coordinates
    center = drawing.length_label_center(0, "60,00")
    assert center[1] - drawing.coordinates[0][1] == pytest.approx(settings.PLAN_LENGTH_OFFSET_MM
           + settings.PLAN_FONT_SIZE_MM / 2 + 1.1)
    root = ET.fromstring(drawing.render())
    assert root.find(".//s:g[@data-kind='legend-axis']", NS).get("display") == "inline"
    items = load_assumptions(
        config, project, 100,
        PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN)).scale,
    )
    assert "bend_radius" in [item.id for item in items] and "symbolic_bends" not in [item.id for item in items]
    assert any("ось — тонкая штрихпунктирная" in item.full.lower() for item in items)
    monkeypatch.setattr(settings, "DRAW_PIPE_AXIS", False)
    assert ET.fromstring(drawing.render()).find(".//s:g[@data-kind='legend-axis']", NS).get("display") == "none"
    project.pipe.outer_diameter_mm = 110
    assert "bend_radius" not in [item.id for item in load_assumptions(
        config, project, 100,
        PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN)).scale,
    )]


def test_specification_header_padding_and_bend_size(route_data, config):
    project = Project.model_validate(route_data)
    drawing = SpecificationDrawing(project, DocumentSet(project, config).get(DocumentId.SPECIFICATION))
    header = TableCell(HEADERS[5], 0, 0, WIDTHS[5], settings.SPEC_HEADER_HEIGHT_MM, True)
    assert header.lines == ["Ед.", "измерения"]
    assert "Ед.\nизме-\nрения" in drawing.table_header_svg() or "изме-" in drawing.table_header_svg()
    assert "⌀110×6,6" in drawing.rows[0][1]
    for row, height in zip(drawing.rows, drawing.calculate_row_heights()):
        lines = TableCell(row[-1], 0, 0, WIDTHS[-1], height, False).lines
        assert height >= len(lines) * settings.TABLE_CELL_LINE_STEP_MM + 2 * settings.SPEC_ROW_VERTICAL_PADDING_MM
        assert all(text_width(line, settings.DEFAULT_FONT_SIZE_MM) < WIDTHS[-1] for line in lines)


def test_profile_placement_and_horizontal_dashes(route_data, config):
    from core.profile import ProfileDrawing
    from core.profile_grid import ProfileGrid
    route_data["pipe"].update(outer_diameter_mm=2200, wall_mm=130)
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    grid = ProfileGrid(drawing)
    assert grid.projection_labels()
    root = ET.fromstring(drawing.render())
    names = root.findall(".//s:text[@data-kind='point-name']", NS)
    assert all(name.get("text-anchor") in ("start", "end") for name in names)
    dashes = root.findall(".//s:text[@data-kind='natural-ground']", NS)
    assert all(element.get("transform") is None for element in dashes)
    shelf = root.find(".//s:g[@data-kind='pipe-label']", NS)
    bounds = tuple(map(float, shelf.get("data-bounds").split()))
    placement = root.find(".//s:g[@id='profile-pipe-label']", NS).get("data-placement")
    if placement == "ok":
        assert drawing.shelf_fits(bounds, *drawing.label_obstacles())
        assert bounds[0] >= drawing.origin_x - settings.PROFILE_POINT_ORIGIN_MM
        assert bounds[2] <= drawing.origin_x + drawing.stations[-1] * drawing.mm_per_meter_x + settings.PROFILE_GRID_RIGHT_PADDING_MM


def test_graphic_height_check_includes_ground_not_only_text(route_data, config):
    from core.profile import ProfileDrawing
    from core.checks.profile import ProfileChecks
    from core.checks.base import CheckContext
    project = Project.model_validate(route_data)
    documents = DocumentSet(project, config)
    root = ET.fromstring(ProfileDrawing(project, documents.get(DocumentId.PROFILE), config).render())
    root.find(".//s:path[@id='ground-line']", NS).set("d", "M 100,19 L 150,30")
    context = CheckContext(project, documents, ".")
    context.roots[DocumentId.PROFILE] = root
    checks = ProfileChecks(context)
    checks.check_profile_field()
    assert context.results[-1].status == "warning"
