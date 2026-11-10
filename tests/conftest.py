import copy
import json

import pytest
from pathlib import Path

from main import load_config


(Path(__file__).resolve().parents[1] / 'tmp').mkdir(exist_ok=True)


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
def config():
    return load_config()


@pytest.fixture
def route_data():
    return copy.deepcopy(REFERENCE_ROUTE)


@pytest.fixture
def write_route(tmp_path):
    def write(data, filename="input.json"):
        path = tmp_path / filename
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path
    return write


@pytest.fixture
def input_file(write_route, route_data):
    return write_route(route_data)
