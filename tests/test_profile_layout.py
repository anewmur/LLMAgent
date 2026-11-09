import copy
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from config import drawing_settings as settings
from core.calculations import load_project
from core.checks.base import CheckContext
from core.checks.profile import ProfileChecks
from core.documents import DocumentSet
from core.formatting import format_slope
from core.models import DocumentId, Project, Status
from config.paths import PROJECT_ROOT
from core.profile import ProfileDrawing
from core.profile_labels import ProfileLabels
from core.release import create_package


NS = {"s": "http://www.w3.org/2000/svg"}


def profile_checks(project, config, svg):
    context = CheckContext(project, DocumentSet(project, config), Path("."))
    context.roots[DocumentId.PROFILE] = ET.fromstring(svg)
    ProfileChecks(context).run()
    return context.results


@pytest.mark.parametrize("value, expected", [(8.01, "8"), (-17.03, "17"),
                                            (-14.2857, "14,3"), (5, "5"), (8.3333, "8,3"),
                                            (8.05, "8"), (8.051, "8,1"), (None, "—")])
def test_slope_format_has_no_sign_and_uses_agreed_tolerance(value, expected):
    assert format_slope(value) == expected


def test_gost_b1_layout_and_shelf(config, tmp_path):
    project, problems = load_project(PROJECT_ROOT / "input/examples/gost_b1.json")
    assert not problems
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    root = ET.fromstring(drawing.render())
    assert drawing.horizontal_scale == 1000
    assert [element.text for element in root.findall(".//s:text[@data-kind='slope']", NS)] == [
        "8,3", "17,2", "14,3", "14,2", "600", "5,1",
    ]
    assert root.find(".//s:text[@data-kind='pipe-description']", NS).text == "Труба стальная ⌀325×7"
    names = root.findall(".//s:text[@data-kind='point-name']", NS)
    assert all(element.get("transform") is None and element.get("text-anchor") in ("start", "end") for element in names)
    assert names[4].get("y") != names[5].get("y")
    shelf = root.find(".//s:g[@data-kind='pipe-label']", NS)
    bounds = tuple(map(float, shelf.get("data-bounds").split()))
    labels, segments = drawing.label_obstacles()
    assert drawing.shelf_fits(bounds, labels, segments)
    # Первый длинный участок тесен: полка ушла к другому 35-метровому участку.
    target_x = float(shelf.find("s:path", NS).get("d").split()[1].split(",")[0])
    assert any(target_x == pytest.approx(drawing.origin_x + (start + end) / 2 * drawing.mm_per_meter_x)
               for start, end in zip(drawing.stations, drawing.stations[1:]))
    bottom = [float(pair.split(",")[1]) for pair in root.find(".//s:path[@id='pipe-bottom-line']", NS).get("d").split()[1::2]]
    assert drawing.datum_y - max(bottom) == pytest.approx(settings.PROFILE_LOWEST_PIPE_GAP_MM)
    result = create_package(project, tmp_path / "output", config)
    assert result["status"] == Status.WARNING
    assert not any(check.name == "profile_text_overlap" and check.status == Status.WARNING for check in result["checks"])
    assert any(check.name == "profile_text_bounds" and "600" in check.message for check in result["checks"])
    assert "Масштабы профиля 1:1000 и 1:100" in (tmp_path / "output/check_report.md").read_text(encoding="utf-8")


@pytest.mark.parametrize("length, expected", [(120, 1000), (360, 2000), (1500, 5000)])
def test_horizontal_scale_is_selected_by_available_width(route_data, config, length, expected):
    route_data["points"] = [dict(route_data["points"][0]), dict(route_data["points"][-1], x=length, y=0)]
    route_data["bends"] = []
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    assert drawing.horizontal_scale == expected
    assert drawing.stations[-1] * drawing.mm_per_meter_x + 76 + settings.PROFILE_GRID_RIGHT_PADDING_MM <= 385
    route_data["points"][-1]["x"] = 10000
    with pytest.raises(ValueError, match="не помещается"):
        ProfileDrawing(Project.model_validate(route_data), DocumentSet(project, config).get(DocumentId.PROFILE), config)


def test_pipe_description_uses_material_dictionary_standard_and_insulation(route_data, config):
    config = copy.deepcopy(config)
    config["profile"]["materials"]["Сталь"]["standard"] = "ГОСТ тест"
    route_data["pipe"].update(material="Сталь", outer_diameter_mm=325, wall_mm=7, insulation="Защитное покрытие")
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    root = ET.fromstring(drawing.render())
    label = root.find(".//s:text[@data-kind='pipe-description']", NS)
    assert label.text == "Труба стальная ⌀325×7 ГОСТ тест"
    assert "SDR" not in label.text and "В1" not in label.text
    assert root.find(".//s:text[@data-kind='insulation']", NS).text == "Защитное покрытие"
    assert all(label.bounds[0] >= label.cell[0] and label.bounds[2] <= label.cell[2]
               for label in ProfileLabels(root).items if label.text == "Труба стальная ⌀325×7 ГОСТ тест")


def test_profile_checks_detect_overlap_cell_overflow_and_high_depth(route_data, config):
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    root = ET.fromstring(drawing.render())
    grid = root.find(".//s:g[@id='profile-grid']", NS)
    slope = root.find(".//s:text[@data-kind='slope']", NS)
    duplicate = copy.deepcopy(slope)
    duplicate.text = "12,0025,00"
    grid.append(duplicate)
    root.find(".//s:text[@data-kind='pipe-description']", NS).text = "Очень длинная труба " * 20
    depth = root.find(".//s:text[@data-kind='depth']", NS)
    depth.set("transform", "translate(217.5 17) rotate(-90)")
    checks = profile_checks(project, config, ET.tostring(root, encoding="unicode"))
    assert any(check.name == "profile_text_overlap" and "12,0025,00" in check.message for check in checks)
    assert any(check.name == "profile_text_bounds" and "Очень длинная" in check.message for check in checks)
    assert any(check.name == "profile_text_bounds" and "над профилем" in check.message for check in checks)
    assert any(check.name == "profile_text_overlap" and settings.TRAINING_LABEL in check.message for check in checks)


def test_pipe_shelf_without_space_reports_warning_instead_of_missing_label(route_data, config):
    route_data["pipe"].update(outer_diameter_mm=250, wall_mm=14.8)
    for point in route_data["points"]:
        point["ground"] = 130
    project = Project.model_validate(route_data)
    drawing = ProfileDrawing(project, DocumentSet(project, config).get(DocumentId.PROFILE), config)
    checks = profile_checks(project, config, drawing.render())
    assert any(check.name == "profile_shelf_space" and check.status == Status.WARNING for check in checks)
    assert not any(check.status == Status.ERROR for check in checks)
