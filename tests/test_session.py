from dataclasses import asdict
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

from core import session as session_module
from core.assumptions import load_assumptions
from core.session import RouteSession
from core.paths import PROJECT_ROOT
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.models import DocumentId
from core.calculations import calculate_route_geometry
from core.formatting import format_pipe_value
from core.settings import BEND_FIELDS_REQUIRED, LOAD_ROUTE_DATA_ERROR
from core.validate import InputValidator


NS = {"s": "http://www.w3.org/2000/svg"}


@pytest.mark.parametrize("status, point_x", [("ok", 60), ("warning", 2)])
def test_release_returns_assumptions_from_report(route_data, write_route, tmp_path, config, status, point_x):
    route_data["points"][1]["x"] = point_x
    if status == "warning":
        config["assumptions"].reverse()
    session = RouteSession(write_route(route_data), tmp_path / "output", config)

    result = session.release()

    assert result["status"] == status, result
    report = (session.output_dir / "check_report.md").read_text(encoding="utf-8")
    section = report.split("## Допущения\n\n", 1)[1].split("\n\n## Ограничения", 1)[0]
    lines = section.strip().splitlines()
    assert lines and all(line.startswith("- ") for line in lines)
    items = load_assumptions(config, session.project, 100)
    assert [line.removeprefix("- ") for line in lines] == [item.full for item in items]
    key_items = [item for item in items if item.key]
    assert {item.id for item in key_items} == {
        "coordinate_system", "network_ground", "bend_material", "profile_insulation", "missing_levels", "pipe_quantity", "symbolic_bends",
    }
    assert result["assumptions"] == [item.short for item in key_items]
    root = ET.parse(session.output_dir / "general.svg").getroot()
    blocks = root.findall(".//s:g[@data-assumption-id]", NS)
    assert [block.get("data-assumption-id") for block in blocks] == [item.id for item in key_items]
    short_texts = [" ".join(" ".join(block.itertext()).split()) for block in blocks]
    assert short_texts == result["assumptions"]
    assert len(lines) == len(items) == 28
    assert len(blocks) == len(result["assumptions"]) == 7
    assert config["assumptions_footer"] in " ".join(root.itertext())


@pytest.mark.parametrize("failure", ["invalid_data", "drawing_does_not_fit"])
def test_failed_release_has_no_assumptions(route_data, write_route, tmp_path, config, failure):
    if failure == "invalid_data":
        route_data["points"][3]["axis"] = None
    else:
        route_data["points"][-1]["x"] = 800
    session = RouteSession(write_route(route_data), tmp_path / "output", config)

    result = session.release()

    assert result["status"] == "error", result
    assert "assumptions" not in result
    assert not session.output_dir.exists()


def test_session_updates_380_accumulates_history_and_restarts(input_file, tmp_path, config):
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder, config)
    assert session.release()["status"] == "ok"
    assert not (folder / "changes.md").exists()
    result = session.update_point("P5", x=300)
    assert result["status"] == "ok", result
    assert "assumptions" not in result
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
    for arguments in ({}, {"unknown": 280}):
        rejected = session.update_point("P5", **arguments)
        assert rejected["status"] == "error"
        assert rejected["problems"][0]["message"] == session_module.FIELDS_REQUIRED
    missing_angle = session.update_point("P5", x=280, bends=[{"at": "P4"}])
    assert missing_angle["status"] == "error"
    assert missing_angle["problems"][0]["message"] == BEND_FIELDS_REQUIRED
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

    assert {key: result[key] for key in ("status", "object_name", "point_count", "length_m")} == {
        "status": "ok", "object_name": "Учебный водопровод, трасса 2", "point_count": 5, "length_m": 250}
    assert result["problems"] == [] and result["checks"]
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


def test_add_and_remove_straight_point_preserves_names_length_and_changes(input_file, tmp_path, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    added = session.add_point("P1a", after="P1", x=90, y=0, ground=102.9, axis=100.35)
    assert added["status"] in ("ok", "warning"), added
    assert [point.id for point in session.project.points] == ["P0", "P1", "P1a", "P2", "P3", "P4", "P5"]
    assert session.calculate_route_length()["length_m"] == 360
    assert session.project.points[2].axis == 100.35
    assert "P1a" in (session.output_dir / "plan.svg").read_text(encoding="utf-8")
    changes = (session.output_dir / "changes.md").read_text(encoding="utf-8")
    assert "Добавление точки P1a" in changes and "None" not in changes and "— → 90,00" in changes
    removed = session.remove_point("P1")
    assert removed["status"] in ("ok", "warning"), removed
    assert [point.id for point in session.project.points] == ["P0", "P1a", "P2", "P3", "P4", "P5"]
    assert session.calculate_route_length()["length_m"] == 360


def test_lateral_insert_is_atomic_and_can_be_retried_with_one_bend(route_data, write_route, tmp_path, config):
    # У обоих соседей новой точки статус концов трассы: новых поворотов в них нет.
    route_data["points"] = [route_data["points"][0], route_data["points"][2]]
    route_data["bends"] = []
    session = RouteSession(write_route(route_data), tmp_path / "output", config)
    assert session.release()["status"] == "ok"
    before = session.project.model_dump()
    files = {path.relative_to(session.output_dir): path.read_bytes() for path in session.output_dir.rglob("*") if path.is_file()}
    rejected = session.add_point("P1a", "P0", 60, 60, 102.6, 100.2)
    assert rejected["status"] == "error" and "Изменение не применено" in rejected["message"]
    assert any(problem["where"] == "P1a" and "90,00 без отвода" in problem["message"] for problem in rejected["problems"])
    assert session.project.model_dump() == before and not session.changes
    assert {path.relative_to(session.output_dir): path.read_bytes() for path in session.output_dir.rglob("*") if path.is_file()} == files
    accepted = session.add_point("P1a", "P0", 60, 60, 102.6, 100.2, bend_angle=90)
    assert accepted["status"] in ("ok", "warning"), accepted
    assert session.calculate_route_length()["length_m"] == pytest.approx(120 * 2 ** 0.5)
    assert [(bend.at, bend.angle_deg) for bend in session.project.bends] == [("P1a", 90)]


@pytest.mark.parametrize("operation, arguments, where, message", [
    ("remove_point", {"name": "P2"}, "P3", "угол отвода"),
    ("remove_point", {"name": "unknown"}, "unknown", "Точка не найдена"),
    ("add_bend", {"at": "P1", "angle_deg": 90}, "P1", "угол отвода"),
    ("remove_bend", {"at": "P2"}, "P2", "без отвода"),
    ("remove_bend", {"at": "P1"}, "P1", "Отвод в этой точке не найден"),
    ("add_bend", {"at": "P2", "angle_deg": 45}, "P2", "угол отвода"),
    ("add_bend", {"at": "P0", "angle_deg": 90}, "P0", "концевой"),
])
def test_invalid_topology_edits_keep_project_and_output(input_file, tmp_path, config, operation, arguments, where, message):
    session = RouteSession(input_file, tmp_path / "output", config)
    assert session.release()["status"] == "ok"
    before = session.project.model_dump()
    files = {path.relative_to(session.output_dir): path.read_bytes() for path in session.output_dir.rglob("*") if path.is_file()}
    result = getattr(session, operation)(**arguments)
    assert result["status"] == "error" and "Изменение не применено" in result["message"]
    assert any(problem["where"] == where and message in problem["message"] for problem in result["problems"])
    assert session.project.model_dump() == before and not session.changes
    assert {path.relative_to(session.output_dir): path.read_bytes() for path in session.output_dir.rglob("*") if path.is_file()} == files


def test_point_move_and_bend_are_applied_together_and_replace_existing_angle(input_file, tmp_path, config):
    import re
    session = RouteSession(input_file, tmp_path / "output", config)
    rejected = session.update_point("P5", y=120)
    assert rejected["status"] == "error" and session.project.points[-1].y == 80
    problem = next(problem for problem in rejected["problems"] if problem["where"] == "P4")
    angle = float(re.search(r"[0-9]+,[0-9]+", problem["message"]).group().replace(",", "."))
    applied = session.update_point("P5", y=120, bends=[{"at": "P4", "angle_deg": angle}])
    assert applied["status"] in ("ok", "warning"), applied
    assert session.project.points[-1].y == 120
    assert session.calculate_route_length()["length_m"] == pytest.approx(280 + (80 ** 2 + 40 ** 2) ** 0.5)
    applied = session.update_point("P5", y=160, bends=[{"at": "P4", "angle_deg": 45}])
    assert applied["status"] in ("ok", "warning"), applied
    assert len(session.project.bends) == 3
    assert [bend.angle_deg for bend in session.project.bends if bend.at == "P4"] == [45]
    assert any(value["name"] == "Угол отвода в P4" for value in applied["changes"]["values"])
    assert session.update_point("P5", y=160, bends=[{"at": "P4", "angle_deg": 45}]) == {
        "status": "ok", "message": "Значения не изменились.",
    }
    assert len(session.changes) == 2


def test_point_move_sets_new_and_existing_bends_in_one_call(input_file, tmp_path, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    before_length = session.calculate_route_length()["length_m"]
    validator = InputValidator(session.project.with_point("P3", y=100))
    validator.validate()
    angles = {name: validator.turn_angle(validator.ids.index(name)) for name in ("P3", "P4")}

    rejected = session.update_point("P3", y=100)

    assert rejected["status"] == "error" and session.project.points[3].y == 80
    messages = {problem["where"]: problem["message"] for problem in rejected["problems"]}
    assert f"по координатам поворот {format_pipe_value(angles['P3'])}" in messages["P3"]
    assert format_pipe_value(angles["P4"]) in messages["P4"]

    bends = [{"at": name, "angle_deg": round(angle, 2)} for name, angle in angles.items()]
    applied = session.update_point("P3", y=100, bends=bends)

    assert applied["status"] in ("ok", "warning"), applied
    assert [(bend.at, bend.angle_deg) for bend in session.project.bends] == [
        ("P2", 90), *((bend["at"], bend["angle_deg"]) for bend in bends),
    ]
    values = {value["name"]: (value["before"], value["after"]) for value in applied["changes"]["values"]}
    assert values["Угол отвода в P3"] == (90, bends[0]["angle_deg"])
    assert values["Угол отвода в P4"] == (None, bends[1]["angle_deg"])
    after_length = calculate_route_geometry(validator.project.points)["length_m"]
    assert after_length != before_length
    assert values["Общая длина трассы"] == pytest.approx((before_length, after_length))
    assert session.calculate_route_length()["length_m"] == pytest.approx(after_length)


@pytest.mark.parametrize("operation", ["add", "remove"])
def test_bend_operations_can_repair_loaded_route(route_data, write_route, tmp_path, config, operation):
    if operation == "add":
        route_data["bends"].pop(0)
    else:
        route_data["points"] = route_data["points"][:3]
        route_data["bends"] = [{"at": "P1", "angle_deg": 90}]
    session = RouteSession(write_route(route_data), tmp_path / "output", config)
    result = session.add_bend("P2", 90) if operation == "add" else session.remove_bend("P1")
    assert result["status"] == "ok", result
    expected = "Добавление отвода в P2" if operation == "add" else "Удаление отвода в P1"
    assert session.changes[-1].title == expected
    assert len(session.project.bends) == (2 if operation == "add" else 0)


def test_bend_replacement_and_angle_only_update_skip_repeated_release(input_file, tmp_path, config, monkeypatch):
    session = RouteSession(input_file, tmp_path / "output", config)
    replaced = session.add_bend("P2", 89.8)
    assert replaced["status"] in ("ok", "warning"), replaced
    assert [(bend.at, bend.angle_deg) for bend in session.project.bends] == [("P2", 89.8), ("P3", 90)]
    assert replaced["changes"]["values"] == [
        {"name": "Угол отвода в P2", "before": 90, "after": 89.8, "unit": "°"},
    ]
    updated = session.update_point("P2", bends=[{"at": "P2", "angle_deg": 90}])
    assert updated["status"] == "ok", updated
    assert [(bend.at, bend.angle_deg) for bend in session.project.bends] == [("P2", 90), ("P3", 90)]
    assert updated["changes"]["values"] == [
        {"name": "Угол отвода в P2", "before": 89.8, "after": 90, "unit": "°"},
    ]
    files = {path.relative_to(session.output_dir): path.read_bytes()
             for path in session.output_dir.rglob("*") if path.is_file()}
    before_changes = session.changes.copy()
    validation = Mock(side_effect=AssertionError("Неизменённые данные не требуют проверки"))
    export = Mock(side_effect=AssertionError("Неизменённые данные не требуют выпуска"))
    monkeypatch.setattr(session_module, "validate_input", validation)
    monkeypatch.setattr(session_module, "create_package", export)
    assert session.add_bend("P2", 90) == {"status": "ok", "message": "Значения не изменились."}
    assert session.update_point("P2", bends=[{"at": "P2", "angle_deg": 90}]) == {
        "status": "ok", "message": "Значения не изменились.",
    }
    assert session.changes == before_changes
    assert {path.relative_to(session.output_dir): path.read_bytes()
            for path in session.output_dir.rglob("*") if path.is_file()} == files
    validation.assert_not_called()
    export.assert_not_called()


def test_ground_update_changes_depth_and_lists_ground_once(input_file, tmp_path, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    result = session.update_point("P3", ground=103.6)
    assert result["status"] == "ok", result
    assert result["changes"]["values"] == [
        {"name": "P3, отметка земли", "before": 103.4, "after": 103.6, "unit": "м"},
    ]
    assert session.project.points[3].ground == 103.6 and session.project.points[3].axis == 100.6
    assert session.calculate_route_length()["length_m"] == 360
    assert "103,60" in (session.output_dir / "profile.svg").read_text(encoding="utf-8")
    assert "P3, отметка земли: **103,40 → 103,60 м**" in (
        session.output_dir / "changes.md"
    ).read_text(encoding="utf-8")


def test_remove_point_rejects_too_few_points(route_data, write_route, tmp_path, config):
    route_data["points"] = route_data["points"][:2]
    route_data["bends"] = []
    session = RouteSession(write_route(route_data), tmp_path / "output", config)
    assert session.release()["status"] == "ok"
    before = session.project.model_dump()
    files = {path.relative_to(session.output_dir): path.read_bytes()
             for path in session.output_dir.rglob("*") if path.is_file()}
    rejected = session.remove_point("P1")
    assert rejected["status"] == "error" and len(session.project.points) == 2
    assert len(rejected["problems"]) == 1 and rejected["problems"][0]["where"] == "points"
    assert "at least 2 items" in rejected["problems"][0]["message"]
    assert session.project.model_dump() == before and not session.changes
    assert {path.relative_to(session.output_dir): path.read_bytes()
            for path in session.output_dir.rglob("*") if path.is_file()} == files
