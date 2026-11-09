from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest

from config import drawing_settings as settings
from core.documents import DocumentSet
from core.checks.plan import PlanChecks
from core.models import DocumentId
from core.plan import PlanDrawing
from core.tables import text_width
from core.validate import validate_input


def test_plan_geometry_scale_direction_and_fit(route_data, config):
    expected = [(77.5, 171), (137.5, 171), (197.5, 171), (197.5, 91), (277.5, 91), (357.5, 91)]
    ns = {"s": "http://www.w3.org/2000/svg"}

    # \u041f\u0435\u0440\u0435\u043d\u043e\u0441 \u0432\u0441\u0435\u0439 \u0442\u0440\u0430\u0441\u0441\u044b \u0432 \u0434\u0440\u0443\u0433\u0443\u044e \u0441\u0438\u0441\u0442\u0435\u043c\u0443 \u043a\u043e\u043e\u0440\u0434\u0438\u043d\u0430\u0442 \u043d\u0435 \u043c\u0435\u043d\u044f\u0435\u0442 \u0435\u0451 \u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044e \u043d\u0430 \u043b\u0438\u0441\u0442\u0435.
    for offset_x, offset_y in [(0, 0), (1000, -500)]:
        data = deepcopy(route_data)
        data["object"].update(project_code="OTHER-03", name="\u0414\u0440\u0443\u0433\u043e\u0439 \u043e\u0431\u044a\u0435\u043a\u0442")
        for point in data["points"]:
            point["x"] += offset_x
            point["y"] += offset_y
        project, problems = validate_input(data)
        assert not problems

        drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN))

        assert drawing.scale == 1000
        assert drawing.sheet.number == ""
        root = ET.fromstring(drawing.render())
        geometry = root.find("s:g[@id='route-geometry']", ns)
        line = geometry.find("s:polyline", ns)
        coordinates = [tuple(map(float, pair.split(","))) for pair in line.get("points").split()]
        assert coordinates == expected
        markers = geometry.findall("s:circle[@data-kind='point-marker']", ns)
        assert [(float(marker.get("cx")), float(marker.get("cy"))) for marker in markers] == coordinates
        x_values = [sheet_x for sheet_x, sheet_y in coordinates]
        y_values = [sheet_y for sheet_x, sheet_y in coordinates]
        assert (min(x_values) + max(x_values)) / 2 == (30 + 405) / 2
        assert (min(y_values) + max(y_values)) / 2 == (35 + 227) / 2
        assert coordinates[1][0] - coordinates[0][0] == 60  # 60 \u043c = 60 \u043c\u043c \u043f\u0440\u0438 1:1000.
        assert coordinates[3][1] < coordinates[2][1]  # \u0411\u043e\u043b\u044c\u0448\u0438\u0435 Y \u043d\u0430\u043f\u0440\u0430\u0432\u043b\u0435\u043d\u044b \u0432\u0432\u0435\u0440\u0445.
        assert not geometry.findall("s:text", ns)  # \u041f\u043e\u0434\u043f\u0438\u0441\u0438 \u043d\u0430\u0445\u043e\u0434\u044f\u0442\u0441\u044f \u0432 \u043e\u0442\u0434\u0435\u043b\u044c\u043d\u043e\u0439 \u0433\u0440\u0443\u043f\u043f\u0435.
        text = " ".join(root.itertext())
        assert "OTHER-03-\u041d\u0412" in text
        assert "\u0414\u0440\u0443\u0433\u043e\u0439 \u043e\u0431\u044a\u0435\u043a\u0442" in text
        assert "1:1000" in text
        labels = root.findall(".//s:text[@data-kind='coordinates']", ns)
        assert [element.get("data-point-id") for element in labels] == [point["id"] for point in data["points"]]
        assert [element.text for element in labels] == [
            f'X={point["x"]:.2f}, Y={point["y"]:.2f}'.replace(".", ",") for point in data["points"]
        ]

    # \u0411\u043e\u043b\u044c\u0448\u0430\u044f \u0442\u0440\u0430\u0441\u0441\u0430 \u043d\u0435 \u0434\u043e\u043b\u0436\u043d\u0430 \u043c\u043e\u043b\u0447\u0430 \u043e\u0431\u0440\u0435\u0437\u0430\u0442\u044c\u0441\u044f \u0438\u043b\u0438 \u043c\u0435\u043d\u044f\u0442\u044c \u043c\u0430\u0441\u0448\u0442\u0430\u0431.
    data["points"][-1]["x"] += 10000
    project, problems = validate_input(data)
    assert not problems
    with pytest.raises(ValueError, match="не помещается"):
        PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN))


def test_plan_labels_follow_calculated_lengths_and_stations(route_data, config):
    ns = {"s": "http://www.w3.org/2000/svg"}
    for p5_x, last_length, last_station in [(280, "80,00", "\u041f\u041a 3+60,00"), (300, "100,00", "\u041f\u041a 3+80,00")]:
        data = deepcopy(route_data)
        data["points"][-1]["x"] = p5_x
        project, problems = validate_input(data)
        assert not problems
        root = ET.fromstring(PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN)).render())
        labels = root.find("s:g[@id='route-labels']", ns)
        names = labels.findall(".//s:text[@data-kind='point-name']", ns)
        assert [(element.get("data-point-id"), element.text) for element in names] == [
            (f"P{index}", {2: "P2 / УП1", 3: "P3 / УП2"}.get(index, f"P{index}")) for index in range(6)
        ]
        stations = labels.findall(".//s:text[@data-kind='station']", ns)
        assert [element.text for element in stations] == [
            "\u041f\u041a 0+00,00", "\u041f\u041a 0+60,00", "\u041f\u041a 1+20,00",
            "\u041f\u041a 2+00,00", "\u041f\u041a 2+80,00", last_station,
        ]
        lengths = labels.findall("s:text[@data-kind='length']", ns)
        assert [element.text for element in lengths] == ["60,00", "60,00", "80,00", "80,00", last_length]
        assert [(element.get("data-start-id"), element.get("data-end-id")) for element in lengths] == [
            (f"P{index}", f"P{index + 1}") for index in range(5)
        ]
        line = root.find("s:g[@id='route-geometry']/s:polyline", ns)
        coordinates = [tuple(map(float, pair.split(","))) for pair in line.get("points").split()]
        assert coordinates[-1][0] - coordinates[0][0] == p5_x
        assert all(30 <= sheet_x <= 405 and 35 <= sheet_y <= 227 for sheet_x, sheet_y in coordinates)
        if p5_x == 300:
            pipe_label = labels.find(".//s:g[@data-kind='pipe-label']", ns)
            pipe_bounds = tuple(map(float, pipe_label.get("data-bounds").split()))
            assert pipe_bounds[1] >= float(lengths[-1].get("y")) + settings.PLAN_LENGTH_OFFSET_MM
        coordinate_labels = labels.findall(".//s:text[@data-kind='coordinates']", ns)
        for (sheet_x, sheet_y), name, station, coordinate in zip(coordinates, names, stations, coordinate_labels):
            assert float(name.get("y")) < float(station.get("y")) < float(coordinate.get("y")) < sheet_y
            assert name.get("x") == station.get("x") == coordinate.get("x")
            assert name.get("text-anchor") == station.get("text-anchor") == coordinate.get("text-anchor")
        assert float(lengths[0].get("y")) > coordinates[0][1]
        vertical_left = float(lengths[2].get("x")) - text_width(lengths[2].text, settings.PLAN_FONT_SIZE_MM) / 2
        assert vertical_left - coordinates[2][0] == pytest.approx(settings.PLAN_LENGTH_OFFSET_MM)
        assert lengths[2].get("text-anchor") == "middle"


def test_plan_symbols_and_legend_use_input(route_data, config):
    ns = {"s": "http://www.w3.org/2000/svg"}
    route_data["bends"].reverse()  # Номера УП следуют трассе, а не порядку записей.
    route_data["pipe"].update(material="ПЭ 100 & тест", outer_diameter_mm=160, wall_mm=9.5)
    route_data["object"]["pipe_material"] = route_data["pipe"]["material"]
    project, problems = validate_input(route_data)
    assert not problems
    root = ET.fromstring(PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN)).render())
    line = root.find("s:g[@id='route-geometry']/s:polyline", ns)
    assert line.get("stroke-width") == "0.7"
    assert line.get("stroke-dasharray") == "6 2"
    markers = root.findall(".//s:circle[@data-kind='point-marker']", ns)
    assert len(markers) == len(project.points)
    assert [marker.get("data-point-id") for marker in markers] == [point.id for point in project.points]
    assert all(marker.get("fill") == "white" for marker in markers)
    assert all(float(marker.get("r")) * 2 == settings.POINT_MARKER_DIAMETER_MM for marker in markers)
    assert all(float(marker.get("stroke-width")) == settings.POINT_MARKER_LINE_WIDTH_MM for marker in markers)
    label = root.find(".//s:g[@data-kind='pipe-label']", ns)
    assert [element.text for element in label.findall("s:text", ns)] == ["В1", "⌀160×9,5"]
    assert "ПЭ 100" not in "".join(label.itertext())
    names = root.findall(".//s:text[@data-kind='point-name']", ns)
    assert [element.text for element in names][2:4] == ["P2 / УП1", "P3 / УП2"]
    legend = root.find("s:g[@id='plan-legend']", ns)
    assert legend is not None
    assert "Условные обозначения" in " ".join(legend.itertext())
    symbol = legend.find("s:path[@data-kind='pipe-symbol']", ns)
    assert symbol.get("stroke-dasharray") == line.get("stroke-dasharray")


def test_plan_non_right_angle_and_conflicting_bend(route_data, config):
    route_data["points"] = route_data["points"][:3]
    for point, (point_x, point_y) in zip(route_data["points"], [(0, 0), (80, 0), (160, 80)]):
        point.update(x=point_x, y=point_y)
    route_data["bends"] = [{"at": "P1", "angle_deg": 45}]
    project, problems = validate_input(route_data)
    assert not problems
    root = ET.fromstring(PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN)).render())
    ns = {"s": "http://www.w3.org/2000/svg"}
    label = root.find(".//s:text[@data-kind='point-name'][@data-point-id='P1']", ns)
    assert label.text == "P1 / УП1 (45°00′)"
    assert label.get("text-anchor") == "end"  # Диагональ идёт вправо вверх, подпись — слева.
    line = root.find("s:g[@id='route-geometry']/s:polyline", ns)
    turn_x = float(line.get("points").split()[1].split(",")[0])
    assert float(label.get("x")) < turn_x

    route_data["bends"][0]["angle_deg"] = 90
    project, problems = validate_input(route_data)
    assert any(problem.blocks_quantities and "угол отвода" in problem.message for problem in problems)


def test_plan_accepts_scale_and_reports_fit_at_that_scale(route_data, config):
    project, problems = validate_input(route_data)
    assert not problems
    drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN), scale=2000)
    assert drawing.mm_per_meter == 0.5
    assert drawing.coordinates[1][0] - drawing.coordinates[0][0] == 30
    assert "1:2000" in drawing.sheet.title
    root = ET.fromstring(drawing.render())
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.find("s:g[@id='route-geometry']", ns).get("data-scale") == "2000"
    with pytest.raises(ValueError, match="не помещается на A3 при масштабе 1:500"):
        PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN), scale=500)
    with pytest.raises(ValueError, match="Масштаб должен быть положительным"):
        PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN), scale=0)


def test_pipe_leader_uses_drawing_field_center(route_data, config):
    project, problems = validate_input(route_data)
    assert not problems
    drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN))
    assert drawing.field_center_x() == (30 + 405) / 2
    for sheet_x in (200, 230):
        drawing.coordinates = [(point_x + sheet_x - drawing.coordinates[2][0], point_y)
                               for point_x, point_y in drawing.coordinates]
        label = ET.fromstring(drawing.draw_pipe_label())
        left, top, right, bottom = map(float, label.get("data-bounds").split())
        assert left > sheet_x if sheet_x < drawing.field_center_x() else right < sheet_x
        assert bottom < (drawing.coordinates[2][1] + drawing.coordinates[3][1]) / 2


def test_point_label_blocks_stay_in_field_with_leaders(route_data, config):
    route_data["points"] = route_data["points"][:2]
    route_data["points"][1].update(x=375, y=192)
    route_data["bends"] = []
    project, problems = validate_input(route_data)
    assert not problems
    drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN), scale=1000)
    root = ET.fromstring(drawing.render())
    ns = {"s": "http://www.w3.org/2000/svg"}
    blocks = root.findall(".//s:g[@data-kind='point-label']", ns)
    assert len(blocks) == 2
    for block in blocks:
        leader = block.find("s:path[@data-kind='point-leader']", ns)
        assert leader is not None and leader.get("data-point-id") == block.get("data-point-id")
        labels = block.findall("s:text", ns)
        assert len(labels) == 3 and len({label.get("text-anchor") for label in labels}) == 1
        assert len({label.get("x") for label in labels}) == 1
        for label in labels:
            font_size = float(label.get("font-size", settings.PLAN_FONT_SIZE_MM))
            width = len(label.text) * settings.TEXT_CHARACTER_WIDTH_FACTOR * font_size
            left = float(label.get("x")) - (width if label.get("text-anchor") == "end" else 0)
            assert settings.PLAN_FIELD_LEFT_MM <= left <= left + width <= 405
            assert settings.PLAN_FIELD_TOP_MM <= float(label.get("y")) - font_size
            assert float(label.get("y")) <= settings.PLAN_FIELD_TOP_MM + settings.PLAN_FIELD_HEIGHT_MM


@pytest.mark.parametrize("end_y, side", [(80, 1), (-80, -1)])
def test_vertical_length_label_has_side_clearance(route_data, config, end_y, side):
    route_data["points"] = route_data["points"][:2]
    route_data["points"][1].update(x=0, y=end_y)
    route_data["bends"] = []
    project, problems = validate_input(route_data)
    assert not problems
    drawing = PlanDrawing(project, DocumentSet(project, config).get(DocumentId.PLAN))
    root = ET.fromstring(drawing.render())
    label = root.find(".//{http://www.w3.org/2000/svg}text[@data-kind='length']")
    left, _, right, _ = bounds = PlanChecks.plan_label_bounds(label, settings.PLAN_FONT_SIZE_MM)
    line_x = drawing.coordinates[0][0]
    assert label.get("text-anchor") == "middle"
    assert (left - line_x if side == 1 else line_x - right) == pytest.approx(settings.PLAN_LENGTH_OFFSET_MM)
    pipe = root.find(".//{http://www.w3.org/2000/svg}g[@data-kind='pipe-label']")
    pipe_bounds = tuple(map(float, pipe.get("data-bounds").split()))
    assert not PlanChecks.rectangles_overlap(bounds, pipe_bounds)
