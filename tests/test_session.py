from dataclasses import asdict
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

from core import session as session_module
from core.session import RouteSession


NS = {"s": "http://www.w3.org/2000/svg"}


def test_session_updates_380_accumulates_history_and_restarts(input_file, tmp_path, config):
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    assert not (folder / "changes.md").exists()
    result = session.update_point("P5", x=300)
    assert result["status"] == "ok", result
    assert session.project.points[-1].x == 300
    assert session.calculate_route_length()["length_m"] == 380
    assert session.calculate_material_quantities()["pipe"]["quantity_m"] == 380
    values = {value["name"]: (value["before"], value["after"]) for value in result["changes"]["values"]}
    assert values == {"P5, X": (280, 300), "Общая длина трассы": (360, 380)}
    assert result["changes"]["sheets"] == ["Общие данные", "План", "Профиль", "Спецификация"]
    plan = ET.parse(folder / "plan.svg").getroot()
    profile = ET.parse(folder / "profile.svg").getroot()
    line = plan.find(".//s:polyline[@id='route-line']", NS)
    coordinates = [tuple(map(float, pair.split(","))) for pair in line.get("points").split()]
    assert max(point_x for point_x, point_y in coordinates) - min(point_x for point_x, point_y in coordinates) == 300
    assert all(30 <= point_x <= 405 and 35 <= point_y <= 227 for point_x, point_y in coordinates)
    line = profile.find(".//s:path[@id='pipe-bottom-line']", NS)
    coordinates = [tuple(map(float, pair.split(","))) for pair in line.get("d").split()[1::2]]
    assert coordinates[-1][0] - coordinates[0][0] == 190
    assert all(30 <= point_x <= 405 and 5 <= point_y <= 81 for point_x, point_y in coordinates)
    text = (folder / "changes.md").read_text(encoding="utf-8")
    assert "P5, X: **280,00 → 300,00 м**" in text
    assert "Общая длина трассы: **360,00 → 380,00 м**" in text
    assert session.update_point("P5", x=320)["status"] == "ok"
    text = (folder / "changes.md").read_text(encoding="utf-8")
    assert len(session.changes) == 2
    assert "## 1." in text and "## 2." in text and "380,00 → 400,00" in text
    result = session.update_point("P3", z=100.65)
    assert result["status"] == "ok"
    assert result["changes"]["sheets"] == ["Общие данные", "План", "Профиль", "Спецификация"]
    assert result["changes"]["values"] == [
        {"name": "P3, отметка оси трубы", "before": 100.6, "after": 100.65, "unit": "м"},
    ]
    assert session.project.points[3].axis == 100.65 and session.project.points[3].ground == 103.4
    assert session.calculate_route_length()["length_m"] == 400 and len(session.changes) == 3
    assert input_file.read_bytes() == original
    fresh = RouteSession(input_file, folder, config)
    assert fresh.release()["status"] == "ok"
    assert fresh.calculate_route_length()["length_m"] == 360
    assert not fresh.changes and not (folder / "changes.md").exists()


def test_unchanged_point_keeps_output_and_history(input_file, tmp_path, monkeypatch, config):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    before_changes = session.changes.copy()
    validation = Mock(side_effect=AssertionError("Неизменённые значения не требуют проверки"))
    export = Mock(side_effect=AssertionError("Неизменённая точка не требует выпуска"))
    monkeypatch.setattr(session_module, "validate_input", validation)
    monkeypatch.setattr(session_module, "create_package", export)

    result = session.update_point("P5", x=280)

    assert result == {"status": "ok", "message": "Значения не изменились."}
    assert session.changes == before_changes
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
    missing = session.update_point("missing", x=280)
    assert missing["status"] == "error" and missing["problems"][0]["message"] == "Точка не найдена."
    validation.assert_not_called()
    export.assert_not_called()


def test_change_sheets_follow_document_list(input_file, tmp_path, monkeypatch, config):
    for doc in config["documents"]:
        doc["short_title"] = "Лист " + doc["id"]
    config["documents"].reverse()
    export = Mock(return_value={
        "status": "ok", "problems": [], "pdf": "test.pdf",
    })
    monkeypatch.setattr(session_module, "create_package", export)
    session = RouteSession(input_file, tmp_path / "output", config)

    assert session.release()["status"] == "ok"
    result = session.update_point("P5", x=300)
    assert result["changes"]["sheets"] == ["Лист specification", "Лист profile", "Лист plan", "Лист general"]
    result = session.change_profile_font(-1)
    assert result["changes"]["sheets"] == ["Лист profile"]
    result = session.update_pipe(material="ПЭ 80")
    assert result["changes"]["sheets"] == ["Лист specification", "Лист profile", "Лист plan", "Лист general"]
    assert result["changes"]["values"] == [
        {"name": "Материал трубы", "before": "ПЭ 100", "after": "ПЭ 80", "unit": ""},
        {"name": "Материал трубы в описании объекта", "before": "ПЭ 100", "after": "ПЭ 80", "unit": ""},
    ]
    assert export.call_count == 4
    assert all(call.args[2] is config for call in export.call_args_list)


@pytest.mark.parametrize("status", ["warning", "error"])
def test_update_accepts_warning_and_rejects_error(input_file, tmp_path, monkeypatch, config, status):
    session = RouteSession(input_file, tmp_path / "output", config)
    before = session.project.model_dump()
    published = {"status": status, "problems": [], "pdf": "test.pdf"}
    export = Mock(return_value=published)
    monkeypatch.setattr(session_module, "create_package", export)

    result = session.update_point("P5", x=300)

    if status == "error":
        assert result == published
        assert session.project.model_dump() == before
        assert not session.changes
    else:
        assert result["status"] == status
        assert session.project is export.call_args.args[0]
        assert session.project.points[-1].x == 300
        assert len(session.changes) == 1
        assert asdict(session.changes[0]) == result["changes"]


@pytest.mark.parametrize("case", ["missing_z", "material_conflict"])
def test_invalid_update_keeps_project_history_and_files(input_file, route_data, tmp_path, monkeypatch, case, config, write_route):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    if case == "material_conflict":
        route_data["pipe"]["material"] = "ПЭ 80"
        bad_input = write_route(route_data, "conflict.json")
        session = RouteSession(bad_input, folder, config)
    before_project = session.project.model_dump()
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    export = Mock(side_effect=AssertionError("Ошибочные данные не должны запускать выпуск"))
    monkeypatch.setattr(session_module, "create_package", export)
    result = session.update_point("P3", z=None) if case == "missing_z" else session.update_point("P5", x=300)
    assert result["status"] == "error"
    assert any(problem["where"] == ("P3" if case == "missing_z" else "pipe") for problem in result["problems"])
    assert session.project.model_dump() == before_project
    assert not session.changes
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
    export.assert_not_called()


def test_pipe_update_resolves_material_conflict(route_data, tmp_path, config, write_route):
    route_data["pipe"]["material"] = "ПЭ 80"
    input_file = write_route(route_data)
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "error"
    assert not folder.exists()

    result = session.update_pipe(material="ПЭ 100")

    assert result["status"] == "ok", result
    assert session.project.pipe.material == session.project.object.pipe_material == "ПЭ 100"
    assert result["changes"]["values"] == [
        {"name": "Материал трубы", "before": "ПЭ 80", "after": "ПЭ 100", "unit": ""},
    ]
    assert result["changes"]["sheets"] == ["Общие данные", "План", "Профиль", "Спецификация"]
    assert "Материал трубы: **ПЭ 80 → ПЭ 100**." in (folder / "changes.md").read_text(encoding="utf-8")
    assert "ПЭ 100" in (folder / "specification.csv").read_text(encoding="utf-8-sig")
    assert (folder / "pdf/package.pdf").is_file()
    assert input_file.read_bytes() == original


def test_pipe_noop_and_errors_keep_project_history_and_files(input_file, tmp_path, config, monkeypatch):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    before_project = session.project.model_dump()
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    validation = Mock(wraps=session_module.validate_input)
    export = Mock(return_value={"status": "error", "message": "Ошибка выпуска"})
    monkeypatch.setattr(session_module, "validate_input", validation)
    monkeypatch.setattr(session_module, "create_package", export)

    assert session.update_pipe(material="ПЭ 100") == {"status": "ok", "message": "Значения не изменились."}
    validation.assert_not_called()
    assert session.update_pipe(unknown="значение")["status"] == "error"
    assert session.update_pipe(outer_diameter=0)["status"] == "error"
    export.assert_not_called()
    assert session.update_pipe(outer_diameter=160, wall_thickness=9.5, standard="ТУ TEST") == export.return_value
    export.assert_called_once()
    assert session.project.model_dump() == before_project
    assert not session.changes
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
