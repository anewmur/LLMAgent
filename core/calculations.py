import json
from copy import deepcopy
from pathlib import Path
from core.validate import validate_input


INPUT_PATH = Path(__file__).resolve().parent.parent/ "input" / "input.json"

def calculate_length(points):
    total = 0.0
    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        total += (dx ** 2 + dy ** 2) ** 0.5
    return total


def calculate_route_length(input_file=INPUT_PATH):
    data = json.loads(input_file.read_text(encoding="utf-8"))
    project, problems = validate_input(data)
    if project is None:
        return {"status": "error", "problems": problems}
    return {
        "status": "ok",
        "length_m": calculate_length(data["points"]),
        "note": "Длина считается только по X и Y в плане. Другие отметки на неё не влияют.",
        "problems_for_later": problems,  # понадобятся для профиля, не для длины
    }


if __name__ == "__main__":
    input_file = Path(__file__).resolve().parent.parent / "input" / "input.json"
    # input_file = Path(__file__).resolve().parent.parent / "input" / "input_no_p3_axis.json"
    answer = calculate_route_length(input_file)
    print(answer)
    assert calculate_route_length()['length_m'] == 360.0