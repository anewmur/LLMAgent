import copy
import json

import pytest


REFERENCE_ROUTE = {'object': {'name': 'Учебный участок водопровода',
            'project_code': 'AI-TEST-01',
            'coordinate_system': 'условная местная, м',
            'pipe_material': 'ПЭ 100'},
 'pipe': {'material': 'ПЭ 100',
          'sdr': 17,
          'outer_diameter_mm': 110,
          'wall_mm': 6.6,
          'standard': None},
 'points': [{'id': 'P0', 'x': 0, 'y': 0, 'ground': 102.4, 'axis': 100.0},
            {'id': 'P1', 'x': 60, 'y': 0, 'ground': 102.8, 'axis': 100.2},
            {'id': 'P2', 'x': 120, 'y': 0, 'ground': 103.0, 'axis': 100.4},
            {'id': 'P3', 'x': 120, 'y': 80, 'ground': 103.4, 'axis': 100.6},
            {'id': 'P4', 'x': 200, 'y': 80, 'ground': 103.8, 'axis': 100.8},
            {'id': 'P5', 'x': 280, 'y': 80, 'ground': 104.0, 'axis': 101.0}],
 'bends': [{'at': 'P2', 'angle_deg': 90}, {'at': 'P3', 'angle_deg': 90}]}


@pytest.fixture
def route_data():
    return copy.deepcopy(REFERENCE_ROUTE)


@pytest.fixture
def input_file(tmp_path, route_data):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(route_data, ensure_ascii=False), encoding="utf-8")
    return path
