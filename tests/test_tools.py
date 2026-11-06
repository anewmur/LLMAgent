import json
from unittest.mock import Mock

import pytest

from agent.tools import HANDLERS, TOOLS
from core import calculations


@pytest.fixture
def source(tmp_path, monkeypatch, route_data):
    path = tmp_path / "route.json"
    path.write_text(json.dumps(route_data, ensure_ascii=False), encoding="utf-8")
    load_project = calculations.load_project
    monkeypatch.setattr(calculations, "load_project", lambda input_file: load_project(path))
    return path


def test_handlers_are_direct_calculation_functions():
    assert HANDLERS == {
        "calculate_route_length": calculations.calculate_route_length,
        "calculate_pipe_levels": calculations.calculate_pipe_levels,
        "calculate_material_quantities": calculations.calculate_material_quantities,
    }
    assert {tool["function"]["name"] for tool in TOOLS} == set(HANDLERS)
    assert all(tool["function"]["parameters"]["properties"] == {} for tool in TOOLS)


@pytest.mark.parametrize("diagonal", [False, True])
def test_lengths_are_consistent_between_tools(source, diagonal):
    if diagonal:
        data = json.loads(source.read_text(encoding="utf-8"))
        for i, point in enumerate(data["points"]):
            point["x"] = i * 1.23456789
            point["y"] = (i % 3) * 2.34567891
        data["bends"] = []  # \u043f\u0440\u043e\u0438\u0437\u0432\u043e\u043b\u044c\u043d\u0430\u044f \u0433\u0435\u043e\u043c\u0435\u0442\u0440\u0438\u044f: \u043e\u0442\u0432\u043e\u0434\u044b \u0438\u0437 \u0438\u0441\u0445\u043e\u0434\u043d\u044b\u0445 \u0434\u0430\u043d\u043d\u044b\u0445 \u043a \u043d\u0435\u0439 \u043d\u0435 \u043e\u0442\u043d\u043e\u0441\u044f\u0442\u0441\u044f
        source.write_text(json.dumps(data), encoding="utf-8")

    route = HANDLERS["calculate_route_length"]()
    quantities = HANDLERS["calculate_material_quantities"]()

    assert route["status"] == quantities["status"] == "ok"
    assert route["length_m"] == pytest.approx(
        sum(s["length_m"] for s in route["sections"]), rel=1e-12, abs=1e-12
    )
    assert route["sections"][0]["start_station_m"] == 0.0
    for previous, current in zip(route["sections"], route["sections"][1:]):
        assert current["start_station_m"] == previous["cumsum_dist_m"]
    assert route["sections"][-1]["cumsum_dist_m"] == route["length_m"]
    assert quantities["pipe"]["quantity_m"] == route["length_m"]
    assert "point_levels" not in route
    assert "bends" not in route


def test_levels_do_not_run_geometry(source, monkeypatch):
    geometry = Mock(side_effect=AssertionError("Geometry should not run"))
    monkeypatch.setattr(calculations, "calculate_route_geometry", geometry)

    result = HANDLERS["calculate_pipe_levels"]()

    assert result["status"] == "ok"
    assert len(result["point_levels"]) == 6
    assert result["point_levels"][3]["bottom_m"] == pytest.approx(100.545)
    geometry.assert_not_called()


def test_tools_read_updated_input(source):
    assert HANDLERS["calculate_route_length"]()["length_m"] == 360
    data = json.loads(source.read_text(encoding="utf-8"))
    data["points"][-1]["x"] = 300
    source.write_text(json.dumps(data), encoding="utf-8")

    route = HANDLERS["calculate_route_length"]()
    quantities = HANDLERS["calculate_material_quantities"]()

    assert route["length_m"] == quantities["pipe"]["quantity_m"] == 380
