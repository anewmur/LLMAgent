from xml.etree import ElementTree as ET

from core.checks.base import CheckContext
from core.checks.plan import PlanChecks
from core.documents import DocumentSet
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.models import DocumentId, Status
from core.plan import PlanDrawing
from core.session import RouteSession
from core.validate import validate_input


NS = {"s": "http://www.w3.org/2000/svg"}


def test_overlap_checks_label_pairs_and_diagonal_route(route_data, tmp_path, config):
    project, problems = validate_input(route_data)
    assert not problems
    checks = PlanChecks(CheckContext(project, DocumentSet(project, config), tmp_path))
    checks.roots["plan"] = ET.fromstring(f'''
        <svg xmlns="http://www.w3.org/2000/svg">
          <g id="route-geometry"><polyline id="route-line" points="0,0 20,20" stroke-width="0.7"/></g>
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
    assert any('пересекаются подписи "P1" и "ПК"' in message for message in messages)
    assert any('подпись "P1" пересекает трассу' in message for message in messages)
    assert not any("FAR" in message or "ROTATED" in message for message in messages)


def test_reference_is_clear_and_close_points_publish_and_commit_warning(input_file, tmp_path, config):
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    reference = session.release()
    assert reference["status"] == "ok", reference
    assert any(check["id"] == "plan_label_overlap" and check["passed"] for check in reference["checks"])
    assert not any(check["level"] == "warning" for check in reference["checks"])

    # P0 и P1 находятся в 2 м друг от друга; блоки с одной стороны действительно пересекаются.
    result = session.update_point("P1", x=2)

    assert result["status"] == "warning", result
    assert "assumptions" not in result
    assert session.project.points[1].x == 2
    assert len(session.changes) == 1
    assert any(message.startswith("План:") for message in result["warnings"])
    assert any('"P0" и "P1"' in message for message in result["warnings"])
    assert any(message.startswith("Профиль:") for message in result["warnings"])
    assert (folder / "pdf/package.pdf").is_file()
    assert (folder / "changes.md").is_file()
    report = (folder / "check_report.md").read_text(encoding="utf-8")
    assert "Результат выпуска: **warning**" in report
    assert "Предупреждение" in report and "plan_label_overlap" in report
    assert "Подписи на плане размещаются по простым правилам. Пересечения обнаруживаются приближённо (по оценке габаритов текста) и не исправляются автоматически." in report
    assert "transform rotate автоматически не проверяются на пересечения" in report
    published = ET.parse(folder / "plan.svg").getroot()
    expected = ET.fromstring(PlanDrawing(session.project, DocumentSet(session.project, config).get(DocumentId.PLAN)).render())
    assert ET.tostring(published.find("s:g[@id='route-labels']", NS)) == ET.tostring(expected.find("s:g[@id='route-labels']", NS))
    assert input_file.read_bytes() == original
