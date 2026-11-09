from dataclasses import asdict
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

from core import session as session_module
from core.session import RouteSession
from core.paths import PROJECT_ROOT
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.models import DocumentId
from core.settings import LOAD_ROUTE_DATA_ERROR


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
    result = session.update_point("P3", axis=100.65)
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


@pytest.mark.parametrize("case", ["missing_axis", "material_conflict"])
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
    result = session.update_point("P3", axis=None) if case == "missing_axis" else session.update_point("P5", x=300)
    assert result["status"] == "error"
    assert result["message"] == (
        "Изменение не применено: новые данные не прошли проверку, текущая трасса не изменилась."
    )
    assert any(problem["where"] == ("P3" if case == "missing_axis" else "pipe") for problem in result["problems"])
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
    invalid = session.update_pipe(outer_diameter=0)
    assert invalid["status"] == "error" and invalid["message"].startswith("Изменение не применено:")
    export.assert_not_called()
    assert session.update_pipe(outer_diameter=160, wall_thickness=9.5, standard="ТУ TEST") == export.return_value
    export.assert_called_once()
    assert session.project.model_dump() == before_project
    assert not session.changes
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files


@pytest.mark.parametrize("operation", ["release", "update"])
def test_sdr_mismatch_keeps_project_history_and_output(input_file, route_data, tmp_path, config,
                                                       write_route, monkeypatch, operation):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    if operation == "release":
        route_data["pipe"]["outer_diameter_mm"] = 160
        session = RouteSession(write_route(route_data, "invalid.json"), folder, config)
    before = session.project.model_dump()
    before_problems = session.problems.copy()
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    export = Mock(side_effect=AssertionError("Несогласованная труба не должна запускать выпуск"))
    monkeypatch.setattr(session_module, "create_package", export)

    result = session.update_pipe(outer_diameter=160) if operation == "update" else session.release()

    assert result["status"] == "error"
    assert any(problem["where"] == "pipe" and "SDR" in problem["message"] for problem in result["problems"])
    assert session.project.model_dump() == before and session.problems == before_problems
    assert not session.changes
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
    export.assert_not_called()


def test_second_route_releases_250_metres_and_updates_without_changing_source(tmp_path, config):
    input_file = PROJECT_ROOT / "input" / "examples" / "route_2.json"
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)

    geometry = session.calculate_route_length()
    assert geometry["length_m"] == 50 + 70 + 50 + 80 == 250
    assert [section["length_m"] for section in geometry["sections"]] == [50, 70, 50, 80]
    assert len(session.project.points) == 5 and len(session.project.bends) == 1
    assert session.project.bends[0].angle_deg == 90
    released = session.release()
    assert released["status"] == "ok", released
    assert (folder / "pdf/package.pdf").is_file() and (folder / "tool_log.md").is_file()

    updated = session.update_point("P4", y=90)
    assert updated["status"] == "ok", updated
    assert session.calculate_route_length()["length_m"] == 50 + 70 + 50 + 90 == 260
    assert "250,00 → 260,00 м" in (folder / "changes.md").read_text(encoding="utf-8")
    assert input_file.read_bytes() == original


def test_tool_journal_escapes_cells_and_new_session_starts_empty(input_file, tmp_path, config):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    session.tool_log.extend([
        {"turn": 1, "tool": "update_pipe", "arguments": '{"material": "А|Б"}\n', "result": {"status": "error"}},
        {"turn": 2, "warning": "Источник не вызывался | проверка"},
    ])

    assert session.release()["status"] == "ok"
    journal = (folder / "tool_log.md").read_text(encoding="utf-8")
    assert "| Вопрос | Инструмент | Аргументы | Статус |" in journal
    assert '| 1 | update_pipe | {"material": "А\\|Б"}<br> | error |' in journal
    assert "| 2 | Предупреждение | Источник не вызывался \\| проверка | warning |" in journal

    fresh = RouteSession(input_file, folder, config)
    assert fresh.release()["status"] == "ok"
    assert fresh.tool_log == []
    journal = (folder / "tool_log.md").read_text(encoding="utf-8")
    assert "update_pipe" not in journal and "Источник не вызывался" not in journal


def test_load_route_replaces_project_and_resets_changes_and_font(input_file, tmp_path, config):
    original = input_file.read_bytes()
    route_file = PROJECT_ROOT / "input" / "examples" / "route_2.json"
    route_bytes = route_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.update_point("P5", x=300)["status"] == "ok"
    assert session.change_profile_font(-1)["status"] == "ok"
    assert session.changes and session.font_size == 2.5
    journal = session.tool_log

    result = session.load_route("input/examples/route_2.json")

    assert result == {"status": "ok", "object_name": "Учебный водопровод, трасса 2", "point_count": 5, "length_m": 250}
    assert session.calculate_route_length()["length_m"] == 250
    assert session.changes == [] and session.font_size == DEFAULT_FONT_SIZE_MM
    assert session.tool_log is journal
    assert session.documents.get(DocumentId.GENERAL)["designation"] == "AI-TEST-02-НВ"
    assert "AI-TEST-02-НВ" in (folder / "general.svg").read_text(encoding="utf-8")
    assert not (folder / "changes.md").exists() and (folder / "pdf/package.pdf").is_file()
    assert input_file.read_bytes() == original and route_file.read_bytes() == route_bytes


@pytest.mark.parametrize("case, path", [
    ("outside", "input/../outside.json"),
    ("missing", "input/missing.json"),
    ("bad_json", "input/route.json"),
    ("invalid_data", "input/route.json"),
])
def test_failed_load_route_preserves_project_and_output(input_file, route_data, tmp_path, config,
                                                         monkeypatch, write_route, case, path):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    before = session.project.model_dump()
    before_documents = session.documents
    before_changes = session.changes
    before_problems = session.problems
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    monkeypatch.setattr(session_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(session_module, "INPUT_DIR", input_dir)
    if case in ("bad_json", "invalid_data"):
        if case == "invalid_data":
            route_data["points"][0]["x"] = None
        route_file = write_route(route_data, "input/route.json")
        if case == "bad_json":
            route_file.write_text("{", encoding="utf-8")

    result = session.load_route(path)

    assert result["status"] == "error" and session.calculate_route_length()["length_m"] == 360
    assert session.project.model_dump() == before and session.documents is before_documents
    assert session.changes is before_changes and session.problems is before_problems
    assert session.font_size == DEFAULT_FONT_SIZE_MM
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files


@pytest.mark.parametrize("case", ["blocked_data", "does_not_fit"])
def test_loaded_route_can_be_corrected_after_failed_release(input_file, route_data, tmp_path, config,
                                                            monkeypatch, write_route, case):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.update_point("P5", x=300)["status"] == "ok"
    assert session.change_profile_font(-1)["status"] == "ok"
    previous_project = session.project
    before_files = {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()}
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    monkeypatch.setattr(session_module, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(session_module, "INPUT_DIR", input_dir)
    if case == "blocked_data":
        route_data["points"][3].pop("axis")
    else:
        route_data["points"][-1]["x"] = 800
    route_file = write_route(route_data, "input/route.json")
    original = route_file.read_bytes()

    result = session.load_route("input/route.json")

    assert result["status"] == "error" and session.project is not previous_project
    assert result["message"] == LOAD_ROUTE_DATA_ERROR
    assert session.changes == [] and session.font_size == DEFAULT_FONT_SIZE_MM
    assert {path.relative_to(folder): path.read_bytes() for path in folder.rglob("*") if path.is_file()} == before_files
    if case == "blocked_data":
        assert any(problem["where"] == "P3" and "axis" in problem["message"] for problem in result["problems"])
        assert session.project.points[3].axis is None and session.project.points[-1].x == 280
        repaired = session.update_point("P3", axis=100.6)
    else:
        assert session.project.points[-1].x == 800
        repaired = session.update_point("P5", x=280)
    assert repaired["status"] == "ok", repaired
    assert session.calculate_route_length()["length_m"] == 360 and not session.problems
    assert (folder / "pdf/package.pdf").is_file() and len(session.changes) == 1
    assert route_file.read_bytes() == original
