from unittest.mock import Mock

from agent.tools import TOOLS
from core import calculations
from core.session import RouteSession


def test_tool_schemas():
    tools = {tool["function"]["name"]: tool["function"] for tool in TOOLS}
    assert set(tools) == {"calculate_route_length", "calculate_pipe_levels", "calculate_material_quantities",
                          "change_profile_font", "update_point", "update_pipe", "load_route", "release_documents"}
    for name in ["calculate_route_length", "calculate_pipe_levels", "calculate_material_quantities"]:
        assert tools[name]["parameters"]["properties"] == {}
    point = tools["update_point"]["parameters"]
    assert point["required"] == ["name"]
    assert set(point["properties"]) == {"name", "x", "y", "axis"}
    assert "null" in point["properties"]["axis"]["type"]
    pipe = tools["update_pipe"]["parameters"]
    assert set(pipe["properties"]) == {"material", "sdr", "outer_diameter", "wall_thickness"}
    assert pipe["required"] == [] and pipe["minProperties"] == 1
    assert pipe["additionalProperties"] is False
    load = tools["load_route"]["parameters"]
    assert load["required"] == ["path"] and load["additionalProperties"] is False
    assert set(load["properties"]) == {"path"} and load["properties"]["path"]["type"] == "string"
    assert pipe["properties"]["material"]["type"] == "string"
    assert all(pipe["properties"][name]["type"] == "number" for name in ["sdr", "outer_diameter", "wall_thickness"])


def test_levels_do_not_run_geometry(input_file, tmp_path, monkeypatch, config):
    session = RouteSession(input_file, tmp_path / "output", config)
    geometry = Mock(side_effect=AssertionError("Geometry should not run"))
    monkeypatch.setattr(calculations, "calculate_route_geometry", geometry)
    assert session.calculate_pipe_levels()["status"] == "ok"
    geometry.assert_not_called()


def test_tools_keep_session_data_when_source_file_changes(input_file, route_data, tmp_path, config, monkeypatch, write_route):
    session = RouteSession(input_file, tmp_path / "output", config)
    validation = Mock(side_effect=AssertionError("Project should not be validated again"))
    monkeypatch.setattr(calculations, "validate_input", validation)
    route_data["points"][-1]["x"] = 300
    assert write_route(route_data) == input_file
    assert session.calculate_route_length()["length_m"] == 360
    assert session.calculate_material_quantities()["pipe"]["quantity_m"] == 360
    assert session.calculate_pipe_levels()["status"] == "ok"
    validation.assert_not_called()
