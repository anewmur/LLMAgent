import json
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest

from core import session as session_module
from core.session import RouteSession


NS = {"s": "http://www.w3.org/2000/svg"}


def test_session_updates_380_accumulates_history_and_restarts(input_file, tmp_path):
    original = input_file.read_bytes()
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder)
    assert session.release()["status"] == "ok"
    assert not (folder / "changes.md").exists()
    result = session.update_point("P5", x=300)
    assert result["status"] == "ok", result
    assert session.project.points[-1].x == 300
    assert session.calculate_route_length()["length_m"] == 380
    assert session.calculate_material_quantities()["pipe"]["quantity_m"] == 380
    values = {v["name"]: (v["before"], v["after"]) for v in result["changes"]["values"]}
    assert values["P5, X"] == (280, 300)
    assert values["Общая длина трассы"] == values["Количество трубы"] == (360, 380)
    assert values["Участок P4–P5, длина"] == (80, 100)
    assert result["changes"]["sheets"] == ["Общие данные", "План", "Профиль", "Спецификация"]
    plan = ET.parse(folder / "plan.svg").getroot()
    profile = ET.parse(folder / "profile.svg").getroot()
    assert plan.get("viewBox") == profile.get("viewBox") == "0 0 420 297"
    line = plan.find(".//s:polyline[@id='route-line']", NS)
    xy = [tuple(map(float, p.split(","))) for p in line.get("points").split()]
    assert max(x for x, y in xy) - min(x for x, y in xy) == 300
    assert all(30 <= x <= 405 and 35 <= y <= 227 for x, y in xy)
    line = profile.find(".//s:path[@id='pipe-bottom-line']", NS)
    xy = [tuple(map(float, p.split(","))) for p in line.get("d").split()[1::2]]
    assert xy[-1][0] - xy[0][0] == 190
    assert all(30 <= x <= 405 and 5 <= y <= 81 for x, y in xy)
    text = (folder / "changes.md").read_text(encoding="utf-8")
    assert "360,00 → 380,00" in text and "80,00 → 100,00" in text
    assert session.update_point("P5", x=320)["status"] == "ok"
    text = (folder / "changes.md").read_text(encoding="utf-8")
    assert len(session.changes) == 2
    assert "## 1." in text and "## 2." in text and "380,00 → 400,00" in text
    result = session.update_point("P3", z=100.65)
    assert result["status"] == "ok" and result["changes"]["sheets"] == ["Профиль"]
    assert session.project.points[3].axis == 100.65 and session.project.points[3].ground == 103.4
    assert session.calculate_route_length()["length_m"] == 400 and len(session.changes) == 3
    assert input_file.read_bytes() == original
    fresh = RouteSession(input_file, folder)
    assert fresh.release()["status"] == "ok"
    assert fresh.calculate_route_length()["length_m"] == 360
    assert not fresh.changes and not (folder / "changes.md").exists()


@pytest.mark.parametrize("case", ["missing_z", "material_conflict"])
def test_invalid_update_keeps_project_history_and_files(input_file, route_data, tmp_path, monkeypatch, case):
    folder = tmp_path / "output"
    session = RouteSession(input_file, folder)
    assert session.release()["status"] == "ok"
    if case == "material_conflict":
        route_data["pipe"]["material"] = "ПЭ 80"
        bad_input = tmp_path / "conflict.json"
        bad_input.write_text(json.dumps(route_data), encoding="utf-8")
        session = RouteSession(bad_input, folder)
    before_project = session.project.model_dump()
    before_files = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    export = Mock(side_effect=AssertionError("Ошибочные данные не должны запускать выпуск"))
    monkeypatch.setattr(session_module, "create_package", export)
    result = session.update_point("P3", z=None) if case == "missing_z" else session.update_point("P5", x=300)
    assert result["status"] == "error"
    assert any(p["where"] == ("P3" if case == "missing_z" else "pipe") for p in result["problems"])
    assert session.project.model_dump() == before_project
    assert not session.changes
    assert {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()} == before_files
    export.assert_not_called()
