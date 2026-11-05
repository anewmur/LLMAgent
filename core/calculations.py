import json
from copy import deepcopy
from pathlib import Path
from core.models import Point
from core.validate import validate_input


INPUT_PATH = Path(__file__).resolve().parent.parent/ "input" / "input.json"

def calculate_route_geometry(points: list[Point]):
    sections = []
    total = 0.0

    for i in range(len(points) - 1):
        a = points[i]
        b = points[i + 1]

        dx = b.x - a.x
        dy = b.y - a.y
        length = (dx ** 2 + dy ** 2) ** 0.5

        total += length

        sections.append({
            "start_id": a.id,
            "end_id": b.id,
            "length_m": length,
            "cumsum_dist_m": total,
        })

    return {
        "length_m": total,
        "sections": sections,
    }


def calculate_route_length(input_file=INPUT_PATH):
    data = json.loads(input_file.read_text(encoding="utf-8"))
    project, problems = validate_input(data)

    if project is None:
        return {"status": "error", "problems": problems}

    if any(problem["blocks_length"] for problem in problems):
        return {"status": "error", "problems": problems}

    geometry = calculate_route_geometry(project.points)

    return {
        "status": "ok",
        "length_m": geometry["length_m"],
        "sections": geometry["sections"],
        "problems_for_later": problems,
    }

if __name__ == "__main__":
    input_file = Path(__file__).resolve().parent.parent / "input" / "input.json"
    # input_file = Path(__file__).resolve().parent.parent / "input" / "input_no_p3_axis.json"
    answer = calculate_route_length(input_file)
    print(answer)
    assert calculate_route_length()['length_m'] == 360.0
