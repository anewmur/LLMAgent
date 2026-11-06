import json
from unittest.mock import Mock

import pytest

from agent.tools import TOOLS
from core import calculations
from core.session import RouteSession


def test_tool_schemas():
    tools = {tool["function"]["name"]: tool["function"] for tool in TOOLS}
    assert set(tools) == {"calculate_route_length", "calculate_pipe_levels", "calculate_material_quantities",
                          "change_profile_font", "update_point", "release_documents"}
    for name in ["calculate_route_length", "calculate_pipe_levels", "calculate_material_quantities"]:
        assert tools[name]["parameters"]["properties"] == {}
    point = tools["update_point"]["parameters"]
    assert point["required"] == ["name"]
    assert set(point["properties"]) == {"name", "x", "y", "z"}
    assert "null" in point["properties"]["z"]["type"]


@pytest.mark.parametrize("diagonal", [False, True])
def test_lengths_are_consistent_between_tools(input_file, route_data, tmp_path, diagonal):
    if diagonal:
        for i, point in enumerate(route_data["points"]):
            point.update(x=i * 1.23456789, y=(i % 3) * 2.34567891)
        route_data["bends"] = []
        input_file.write_text(json.dumps(route_data), encoding="utf-8")
    session = RouteSession(input_file, tmp_path / "output")
    route = session.calculate_route_length()
    quantities = session.calculate_material_quantities()
    assert route["status"] == quantities["status"] == "ok"
    assert route["length_m"] == pytest.approx(sum(s["length_m"] for s in route["sections"]), rel=1e-12, abs=1e-12)
    assert route["sections"][0]["start_station_m"] == 0
    for before, after in zip(route["sections"], route["sections"][1:]):
        assert after["start_station_m"] == before["cumsum_dist_m"]
    assert route["sections"][-1]["cumsum_dist_m"] == quantities["pipe"]["quantity_m"]


def test_levels_do_not_run_geometry(input_file, monkeypatch):
    session = RouteSession(input_file)
    geometry = Mock(side_effect=AssertionError("Geometry should not run"))
    monkeypatch.setattr(calculations, "calculate_route_geometry", geometry)
    assert session.calculate_pipe_levels()["status"] == "ok"
    geometry.assert_not_called()


def test_tools_keep_session_data_when_source_file_changes(input_file, route_data):
    session = RouteSession(input_file)
    route_data["points"][-1]["x"] = 300
    input_file.write_text(json.dumps(route_data), encoding="utf-8")
    assert session.calculate_route_length()["length_m"] == 360
    assert session.calculate_material_quantities()["pipe"]["quantity_m"] == 360
