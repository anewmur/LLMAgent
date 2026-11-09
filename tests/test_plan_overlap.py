import math
from xml.etree import ElementTree as ET

from core.checks.base import CheckContext
from core.checks.plan import PlanChecks
from core.documents import DocumentSet
from config.drawing_settings import DEFAULT_FONT_SIZE_MM, PLAN_FONT_SIZE_MM, PLAN_LENGTH_OFFSET_MM
from core.models import DocumentId, Status
from core.plan import PlanDrawing
from core.session import RouteSession
from core.validate import InputValidator, validate_input


NS = {"s": "http://www.w3.org/2000/svg"}


def test_overlap_checks_label_pairs_and_diagonal_route(route_data, tmp_path, config):
    project, problems = validate_input(route_data)
    assert not problems
    checks = PlanChecks(CheckContext(project, DocumentSet(project, config), tmp_path))
    checks.roots["plan"] = ET.fromstring(f'''
        <svg xmlns="http://www.w3.org/2000/svg">
          <g id="route-geometry" data-scale="1000"><polyline id="route-line" points="0,0 20,20" stroke-width="0.7"/></g>
          <g id="route-labels" font-size="{DEFAULT_FONT_SIZE_MM}">
            <text data-kind="point-name" x="10" y="13.5">P1</text>
            <text data-kind="station" data-point-id="P2" x="11" y="13.5">ПК</text>
            <text data-kind="coordinates" x="0" y="12">FAR</text>
            <text data-kind="pipe-label" x="0" y="10" transform="translate(0 0) rotate(45)">ROTATED</text>
          </g>
        </svg>
    ''')

    checks.check_plan_label_overlap()

    assert all(check.name == "plan_label_overlap" and check.status == Status.WARNING for check in checks.results)
    messages = [check.message for check in checks.results]
    assert any('пересекаются или слишком близки подписи "P1" и "ПК"' in message for message in messages)
    assert any('подпись "P1" пересекает трассу' in message for message in messages)
    assert not any("FAR" in message or "ROTATED" in message for message in messages)


def test_pipe_shelf_rectangle_participates_in_overlap_check(route_data, tmp_path, config):
    project, problems = validate_input(route_data)
    assert not problems
    documents = DocumentSet(project, config)
    root = ET.fromstring(PlanDrawing(project, documents.get(DocumentId.PLAN)).render())
    shelf = root.find(".//s:g[@data-kind='pipe-label']", NS)
    left, top, right, bottom = map(float, shelf.get("data-bounds").split())
    name = root.find(".//s:text[@data-kind='point-name']", NS)
    name.set("x", str((left + right) / 2))
    name.set("y", str((top + bottom) / 2))
    checks = PlanChecks(CheckContext(project, documents, tmp_path))
    checks.roots[DocumentId.PLAN] = root
    checks.check_plan_label_overlap()
    assert any(check.status == Status.WARNING and "полка трубы" in check.message for check in checks.results)


def test_reference_is_clear_and_close_points_publish_and_commit_warning(input_file, tmp_path, config):
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    reference = session.release()
    assert reference["status"] == "ok", reference
    assert any(check["id"] == "plan_label_overlap" and check["passed"] for check in reference["checks"])
    assert not any(check["level"] == "warning" for check in reference["checks"])

    # Блоки плана разносятся; слишком близкие точки профиля по-прежнему дают предупреждение.
    result = session.update_point("P1", x=2)

    assert result["status"] == "warning", result
    assert result["assumptions_count"] >= len(result["assumptions"]) > 0
    assert session.project.points[1].x == 2
    assert len(session.changes) == 1
    assert not any(message.startswith("План:") for message in result["warnings"])
    assert any(message.startswith("Профиль:") for message in result["warnings"])
    assert (folder / "pdf/package.pdf").is_file()
    assert (folder / "changes.md").is_file()
    report = (folder / "check_report.md").read_text(encoding="utf-8")
    assert "Результат выпуска: **warning**" in report
    assert "Предупреждение" in report and "plan_label_overlap" in report
    overlap_note = next(item for item in config["assumptions"] if item["id"] == "label_overlap")
    assert overlap_note["full"] in report
    assert "transform rotate автоматически не проверяются на пересечения" not in report
    published = ET.parse(folder / "plan.svg").getroot()
    expected = ET.fromstring(PlanDrawing(session.project, DocumentSet(session.project, config).get(DocumentId.PLAN)).render())
    assert ET.tostring(published.find("s:g[@id='route-labels']", NS)) == ET.tostring(expected.find("s:g[@id='route-labels']", NS))
    assert input_file.read_bytes() == original


def test_slanted_length_label_keeps_gap_from_route(input_file, tmp_path, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    validator = InputValidator(session.project.with_point("P3", x=140))
    validator.validate()
    bends = [{"at": name, "angle_deg": round(validator.turn_angle(validator.ids.index(name)), 2)}
             for name in ("P2", "P3")]

    result = session.update_point("P3", x=140, bends=bends)

    assert result["status"] == "ok", result
    root = ET.parse(session.output_dir / "plan.svg").getroot()
    line = root.find(".//s:polyline[@id='route-line']", NS)
    points = [tuple(map(float, pair.split(","))) for pair in line.get("points").split()]
    labels = root.findall(".//s:text[@data-kind='length']", NS)
    farthest = {}
    for label, start, end in zip(labels, points, points[1:]):
        left, top, right, bottom = PlanChecks.plan_label_bounds(label, PLAN_FONT_SIZE_MM)
        # Расстояния углов рамки до прямой участка; положительные — на стороне нормали, где стоят подписи.
        distances = [((end[0] - start[0]) * (corner_y - start[1]) - (end[1] - start[1]) * (corner_x - start[0]))
                     / math.dist(start, end) for corner_x in (left, right) for corner_y in (top, bottom)]
        assert min(distances) >= PLAN_LENGTH_OFFSET_MM - 1e-6, label.text
        farthest[label.get("data-start-id")] = max(distances)
    pipe = root.find(".//s:g[@data-kind='pipe-label']", NS)
    pipe_bounds = tuple(map(float, pipe.get("data-bounds").split()))
    for label in root.findall(".//s:text[@data-kind='length']", NS):
        assert not PlanChecks.rectangles_overlap(pipe_bounds, PlanChecks.plan_label_bounds(label, PLAN_FONT_SIZE_MM))
