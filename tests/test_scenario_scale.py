import json
from types import SimpleNamespace
from unittest.mock import Mock
from xml.etree import ElementTree as ET

import pytest
from openai.types.chat import ChatCompletionMessage

from config import drawing_settings as settings
from core.models import DocumentId, Project, Status, ProblemCode
from core.documents import DocumentSet
from core.assumptions import load_assumptions
from core.general import GeneralData
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.session import RouteSession
from config.paths import PROJECT_ROOT
from config.settings import MISSING_AXIS_MESSAGE, RELEASE_REFUSED_STATUS
from agent.runtime import RouteAgent
from agent.tools import ToolName
from main import SYSTEM_PROMPT_PATH

NS = {"s": "http://www.w3.org/2000/svg"}


def response(content=None, tool=None, values=None):
    calls = [{"id": "call", "type": "function", "function": {
        "name": tool, "arguments": json.dumps(values or {}),
    }}] if tool else None
    return SimpleNamespace(choices=[SimpleNamespace(message=ChatCompletionMessage(
        role="assistant", content=content, tool_calls=calls))])


@pytest.mark.parametrize("operation", ["load", "remove"])
def test_missing_axis_paths_have_same_refusal_and_recover(input_file, tmp_path, config, operation):
    session = RouteSession(input_file, tmp_path / "output", config)
    assert session.release()["status"] == Status.OK
    client = Mock()
    first_tool, first_values = ((ToolName.LOAD_ROUTE, {"path": "input/examples/no_p3.json"}) if operation == "load"
                               else (ToolName.UPDATE_POINT, {"name": "P3", "axis": None}))
    client.chat.completions.create.side_effect = [
        response(tool=first_tool, values=first_values),
        response(content="Комплект выпущен."),
        response(tool=ToolName.UPDATE_POINT, values={"name": "P3", "axis": 100.6}),
        response(content="Комплект выпущен."),
    ]
    agent = RouteAgent(client, {ToolName.LOAD_ROUTE: session.load_route, ToolName.UPDATE_POINT: session.update_point},
                       SYSTEM_PROMPT_PATH.read_text(encoding="utf-8"), tool_log=session.tool_log)
    answer = agent.ask("Выпусти комплект без отметки оси P3")
    assert "Комплект не выпущен" in answer and "P3" in answer and "Задайте" in answer
    result = session.tool_log[0]["result"]
    assert result["status"] == Status.ERROR and result["released"] is False
    problem = next(problem for problem in result["problems"] if problem["code"] == ProblemCode.MISSING_AXIS)
    assert problem["where"] == "P3" and problem["message"] == MISSING_AXIS_MESSAGE
    assert session.project.points[3].axis is None
    session.save_tool_log()
    assert {path.name for path in session.output_dir.iterdir()} == {"check_report.md", "tool_log.md"}
    report = (session.output_dir / "check_report.md").read_text(encoding="utf-8")
    assert RELEASE_REFUSED_STATUS in report and "missing_axis" in report and MISSING_AXIS_MESSAGE in report
    assert not list(session.output_dir.glob("*.svg")) and not list(session.output_dir.glob("*.csv"))
    assert not (session.output_dir / "pdf").exists()
    assert "Комплект выпущен" in agent.ask("Задай отметку оси P3 = 100,6 и обнови комплект")
    assert session.tool_log[-1]["result"]["status"] == Status.OK
    assert session.project.points[3].axis == 100.6
    assert (session.output_dir / "pdf/package.pdf").is_file()
    assert RELEASE_REFUSED_STATUS not in (session.output_dir / "check_report.md").read_text(encoding="utf-8")
    assert not any("warning" in entry for entry in session.tool_log)


@pytest.mark.parametrize("last_x, expected_scale", [(280, 1000), (400, 2000)])
def test_plan_auto_scale_releases_and_matches_stamp(route_data, write_route, tmp_path, config, last_x, expected_scale):
    route_data["points"][-1]["x"] = last_x
    session = RouteSession(write_route(route_data), tmp_path / "output", config)
    result = session.release()
    assert result["status"] != Status.ERROR, result
    assert result["released"] is True
    root = ET.parse(session.output_dir / "plan.svg").getroot()
    assert root.find("s:g[@id='route-geometry']", NS).get("data-scale") == str(expected_scale)
    stamp = root.find(".//s:text[@x='100'][@y='35.5']", NS)
    assert f"(1:{expected_scale})" in "".join(stamp.itertext())
    assert all(check["level"] != "error" for check in result["checks"])
    assert all(check["passed"] for check in result["checks"] if check["id"] == "plan_label_overlap")


@pytest.mark.parametrize("diameter, wall, dashed", [(110, 6.6, True), (250, 14.8, True),
                                                   (2200, 130, True), (110, 6.6, False)])
def test_line_notes_follow_both_drawings(route_data, config, monkeypatch, diameter, wall, dashed):
    route_data["pipe"].update(outer_diameter_mm=diameter, wall_mm=wall)
    if not dashed:
        monkeypatch.setattr(settings, "PLAN_ROUTE_DASHARRAY_MM", "")
    project = Project.model_validate(route_data)
    documents = DocumentSet(project, config)
    plan = PlanDrawing(project, documents.get(DocumentId.PLAN))
    profile = ProfileDrawing(project, documents.get(DocumentId.PROFILE), config)
    items = load_assumptions(config, project, profile.vertical_scale, plan.scale)
    general = GeneralData(project, documents, config, items)
    note = general.notes()[-1]
    assert ("На плане труба показана двумя сплошными" in note) == (plan.line_count == 2)
    assert ("на профиле — двумя сплошными" in note) == profile.two_lines
    if plan.line_count == 1:
        assert ("одной штриховой" in note) == dashed
    root = ET.fromstring(plan.render())
    assert root.find("s:g[@id='route-geometry']", NS).get("data-line-count") == str(plan.line_count)
    assert (ET.fromstring(profile.render()).find(".//s:path[@id='pipe-top-line']", NS) is not None) == profile.two_lines
    assert note in " ".join(" ".join(ET.fromstring(general.render()).itertext()).split())
