from pathlib import Path
from xml.etree import ElementTree as ET

from config import drawing_settings as settings
from core.calculations import load_project
from core.documents import DocumentSet
from core.label_geometry import labels_too_close
from core.models import Project, DocumentId
from config.paths import PROJECT_ROOT
from core.profile import ProfileDrawing
from core.profile_grid import ProfileGrid
from core.specification import SpecificationDrawing, WIDTHS
from core.tables import text_width

NS = {"s": "http://www.w3.org/2000/svg"}


def test_common_gap_and_point_name_stagger(config):
    assert labels_too_close((0, 0, 5, 5), (5.9, 0, 10, 5))
    assert not labels_too_close((0, 0, 5, 5), (6, 0, 10, 5))
    assert not labels_too_close((0, 0, 5, 5), (5.8, 5.8, 10, 10))
    project, _ = load_project(PROJECT_ROOT / "input/examples/gost_b1.json")
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    root = ET.fromstring(drawing.render())
    names = root.findall(".//s:text[@data-kind='point-name']", NS)
    assert names[0].get("y") != names[1].get("y")


def test_depth_stays_inside_field_when_no_free_height(route_data, config):
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    grid = ProfileGrid(drawing)
    occupied = [(0, 20, 1000, 1000)]
    grid.depth_baseline(100, 22, 4.1, occupied)
    assert occupied[-1][1] >= settings.PROFILE_TEXT_TOP_MM
    for point in project.points:
        point.ground = 130
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    root = ET.fromstring(drawing.render())
    assert root.findall(".//s:text[@data-kind='depth'][@data-placement='warning']", NS)
    assert all(label.bounds[1] >= settings.PROFILE_TEXT_TOP_MM for label in ProfileGrid(drawing).projection_labels())


def test_scale_labels_block_shelf_and_match_rendered_text(route_data, config):
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    grid = ProfileGrid(drawing)
    obstacles, segments = drawing.label_obstacles()
    title = next(label for label in obstacles if label.text == "Масштаб:")
    assert not drawing.shelf_fits(title.bounds, obstacles, segments)
    root = ET.fromstring(drawing.render())
    texts = [element.text for element in root.findall(".//s:g[@id='profile-grid']/s:text", NS)]
    assert all(value in texts for value, baseline in grid.scale_labels())


def test_spec_header_has_margin_and_both_rows_share_size(route_data, config):
    project = Project.model_validate(route_data)
    drawing = SpecificationDrawing(project, DocumentSet(project, config).get(DocumentId.SPECIFICATION))
    assert "⌀110×6,6" in drawing.rows[0][1] and "⌀110×6,6" in drawing.rows[1][1]
    root = ET.fromstring('<svg xmlns="http://www.w3.org/2000/svg">' + drawing.table_header_svg() + '</svg>')
    texts = [element.text for element in root.findall('s:text', NS)]
    assert all(value in texts for value in ["Ед.", "изме-", "рения"])
    assert max(text_width(value, settings.DEFAULT_FONT_SIZE_MM) for value in ["Ед.", "изме-", "рения"]) <= WIDTHS[5] - 2 * settings.PROFILE_CELL_PADDING_MM
