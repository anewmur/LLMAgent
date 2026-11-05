import json
from copy import deepcopy
from pathlib import Path


def calculate_length(points):
    total = 0.0
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        total += (dx ** 2 + dy ** 2) ** 0.5
    return total


def calculate_route_length():           # инструмент для агента
    INPUT_PATH = Path(__file__).resolve().parent.parent/ "input" / "input.json"
    data = json.loads(INPUT_PATH.read_text(encoding="utf-8"))
    length_m = calculate_length(data["points"])
    return {"status": "ok",
            "length_m": length_m}



if __name__ == "__main__":
    answer = calculate_route_length()
    print(answer)
    assert calculate_route_length()['length_m'] == 360.0