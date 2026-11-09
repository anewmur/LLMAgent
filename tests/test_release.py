from unittest.mock import Mock
from xml.etree import ElementTree as ET

from pypdf import PdfReader
import pytest

from core import calculations, release as release_module
from core.assumptions import load_assumptions
from core.checks import base as checks_module
from core.documents import DocumentSet
from core.formatting import format_pipe_value
from core.models import Status
from core.package_checks import PackageChecks
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.release import create_package
from core.session import RouteSession
from core.validate import validate_input


NS = {"s": "http://www.w3.org/2000/svg"}


def test_release_uses_project_and_detects_tampering(route_data, tmp_path, config, monkeypatch):
    folder = tmp_path / "output"
    for p5_x, diameter, wall, length in [(280, 110, 6.6, "360,00"), (300, 160, 9.5, "380,00")]:
        for stale in ["old.svg", "changes.md", "pdf/NV.pdf", "old/nested/preview.png"]:
            path = folder / stale
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old release")
        route_data["points"][-1]["x"] = p5_x
        route_data["pipe"].update(outer_diameter_mm=diameter, wall_mm=wall)
        route_data["object"].update(project_code="OTHER-07", name="Другой объект $100 & участок")
        project, _ = validate_input(route_data)
        with monkeypatch.context() as patch:
            validation = Mock(side_effect=AssertionError("Готовый проект не проверяется повторно"))
            patch.setattr(calculations, "validate_input", validation)
            result = create_package(project, folder, config)
            validation.assert_not_called()
        assert result["status"] == "ok", result
        assert all(check.status == Status.OK for check in result["checks"])
        expected = {"general.svg", "plan.svg", "profile.svg", "specification.svg", "specification.csv", "check_report.md"}
        expected.update("pdf/" + name + ".pdf" for name in ["general", "plan", "profile", "specification", "package"])
        assert {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_file()} == expected
        assert {path.relative_to(folder).as_posix() for path in folder.rglob("*") if path.is_dir()} == {"pdf"}
        report = (folder / "check_report.md").read_text(encoding="utf-8")
        assert "## Допущения" in report and "## Ограничения" in report
        items = load_assumptions(config, project, 100)
        assert all(item.full in report for item in items)
        assert "Отводы включены в спецификацию вопреки ГОСТ 21.704 п. 7.4" in report
        assert ("Вершины трассы без колодцев показаны кружком; отдельного обозначения "
                "ГОСТ 21.704-2011 для них не устанавливает (п. 3.6, 5.1.2).") in report
        assert f"Труба ⌀{diameter} при 1:100" in report
        assert length in (folder / "specification.csv").read_text(encoding="utf-8-sig")
        assert len(PdfReader(folder / "pdf/package.pdf").pages) == 4
        for stem, number, total in [("general", "1", "3"), ("plan", "2", ""), ("profile", "3", ""), ("specification", "", "1")]:
            root = ET.parse(folder / (stem + ".svg")).getroot()
            if stem == "general":
                text = " ".join(" ".join(root.itertext()).split())
                assert all(item.short in text for item in items if item.key)
                notes = root.findall(".//s:g[@id='general-notes']/s:text", NS)
                assert len(notes) == len(config["general_notes"])
                pipe_note = " ".join(" ".join(notes[2].itertext()).split())
                assert pipe_note == (f"Проектируемая сеть В1 — подземный напорный водопровод из труб "
                                     f"ПЭ 100 SDR 17 {diameter}×{format_pipe_value(wall)}. Длина трассы — {length} м.")
            assert (root.find(".//s:text[@x='157.5'][@y='36.5']", NS).text or "") == number
            assert (root.find(".//s:text[@x='175'][@y='36.5']", NS).text or "") == total
    path = folder / "profile.svg"
    value = ET.parse(path).getroot().find(".//s:text[@data-kind='bottom-level']", NS).text
    path.write_text(path.read_text(encoding="utf-8").replace(f'>{value}<', '>999,99<'), encoding="utf-8")
    geometry = Mock(wraps=checks_module.calculate_route_geometry)
    levels = Mock(wraps=checks_module.calculate_point_levels)
    monkeypatch.setattr(checks_module, "calculate_route_geometry", geometry)
    monkeypatch.setattr(checks_module, "calculate_point_levels", levels)
    checker = PackageChecks(project, DocumentSet(project, config), folder)
    checks = checker.run()
    assert geometry.call_count == levels.call_count == 1
    assert checker.run() == checks
    assert geometry.call_count == levels.call_count == 2
    assert next(check.status for check in checks if check.name == "profile_values") != Status.OK


def test_release_preserves_drawing_scales_in_stamp_geometry_and_report(route_data, tmp_path, config, monkeypatch):
    route_data["pipe"].update(outer_diameter_mm=250, wall_mm=14.8)
    project, problems = validate_input(route_data)
    assert not problems
    monkeypatch.setattr(release_module, "PlanDrawing", lambda project, document: PlanDrawing(project, document, scale=2000))
    monkeypatch.setattr(release_module, "ProfileDrawing", lambda project, document, config, font_size: ProfileDrawing(
        project, document, config, font_size, horizontal_scale=4000, vertical_scale=200,
    ))
    folder = tmp_path / "output"

    result = create_package(project, folder, config)

    assert result["status"] == "warning", result
    assert any(check.name == "plan_label_overlap" and check.status == Status.WARNING for check in result["checks"])
    assert not any(check.status == Status.ERROR for check in result["checks"])
    plan = ET.parse(folder / "plan.svg").getroot()
    stamp_title = plan.find(".//s:text[@x='100'][@y='35.5']", NS)
    assert "".join(stamp_title.itertext()) == "План сетей водоснабжения (1:2000)"
    assert "(1:2000)" in PdfReader(folder / "pdf/plan.pdf").pages[0].extract_text()
    profile = ET.parse(folder / "profile.svg").getroot()
    geometry = profile.find("s:g[@id='profile-geometry']", NS)
    assert geometry.get("data-horizontal-scale") == "4000"
    assert geometry.get("data-vertical-scale") == "200"
    assert geometry.find("s:path[@id='pipe-top-line']", NS) is None
    assert profile.find(".//s:text[@data-kind='horizontal-scale']", NS).text == "по горизонтали 1:4000"
    assert profile.find(".//s:text[@data-kind='vertical-scale']", NS).text == "по вертикали 1:200"
    assert "Труба ⌀250 при 1:200 = 1,25 мм < 2 мм" in (folder / "check_report.md").read_text(encoding="utf-8")
    items = load_assumptions(config, project, 200)
    note = next(item for item in items if item.id == "pipe_note")
    assert note.short == "Труба ⌀250 на профиле — одной линией"
    assert note.short not in result["assumptions"]


@pytest.mark.parametrize("case", ["missing_level", "material_conflict", "bend_conflict"])
def test_invalid_project_does_not_replace_documents(route_data, tmp_path, case, config, write_route):
    project, _ = validate_input(route_data)
    folder = tmp_path / "output"
    assert create_package(project, folder, config)["status"] == "ok"
    before = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    if case == "missing_level":
        route_data["points"][3]["axis"] = None
    elif case == "material_conflict":
        route_data["pipe"]["material"] = "ПЭ 80"
    else:
        route_data["bends"][0]["angle_deg"] = 45
    input_file = write_route(route_data, "invalid.json")
    result = RouteSession(input_file, folder, config).release()
    assert result["status"] == "error" and result["problems"]
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before
