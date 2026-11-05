import json
from collections import Counter
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
            "slope_per_mille": calculate_slope(a, b, length),
        })

    # Общий итог выводим из сохранённых длин, не считаем отдельной формулой.
    total = sum(section["length_m"] for section in sections)
    if sections:
        sections[-1]["cumsum_dist_m"] = total

    return {
        "length_m": total,
        "average_slope_per_mille": calculate_slope(points[0], points[-1], total),
        "sections": sections,
    }


def load_project(input_file=INPUT_PATH):
    data = json.loads(input_file.read_text(encoding="utf-8"))
    return validate_input(data)


def calculate_route_length(input_file=INPUT_PATH):
    project, problems = load_project(input_file)

    if project is None:
        return {"status": "error", "problems": problems}

    if any(problem["blocks_length"] for problem in problems):
        return {"status": "error", "problems": problems}

    geometry = calculate_route_geometry(project.points)

    return {
        "status": "ok",
        "length_m": geometry["length_m"],
        "average_slope_per_mille": geometry["average_slope_per_mille"],
        "sections": geometry["sections"],
        "problems": problems,
    }

def calculate_pipe_levels(input_file=INPUT_PATH):
    project, problems = load_project(input_file)
    if project is None:
        return {"status": "error", "problems": problems}
    return {
        "status": "ok",
        "point_levels": calculate_point_levels(
            project.points, project.pipe.outer_diameter_mm
        ),
        "problems": problems,
    }


def calculate_material_quantities(input_file=INPUT_PATH):
    project, problems = load_project(input_file)
    if project is None or any(p["blocks_length"] for p in problems):
        return {"status": "error", "problems": problems}
    blocking = [p for p in problems if p["blocks_quantities"]]
    if blocking:
        return {"status": "error", "problems": blocking}

    geometry = calculate_route_geometry(project.points)
    bend_counts = Counter(bend.angle_deg for bend in project.bends)
    return {
        "status": "ok",
        "pipe": {
            "material": project.pipe.material,
            "sdr": project.pipe.sdr,
            "outer_diameter_mm": project.pipe.outer_diameter_mm,
            "wall_mm": project.pipe.wall_mm,
            "quantity_m": geometry["length_m"],
        },
        "bends": [
            {"angle_deg": angle, "quantity_pcs": count}
            for angle, count in sorted(bend_counts.items())
        ],
        "problems": problems,
    }


def calculate_point_levels(points: list[Point], outer_diameter_mm: float):
    # расчёт высотных значений в каждой точке: отметки наружного низа трубы и глубины от земли до этого низа.
    radius_m = outer_diameter_mm / 2000
    levels = []

    for point in points:
        bottom = None
        depth = None

        if point.axis is not None:
            bottom = point.axis - radius_m
            if point.ground is not None:
                depth = point.ground - bottom

        levels.append({
            "point_id": point.id,
            "bottom_m": bottom,
            "depth_to_bottom_m": depth,
        })

    return levels


def calculate_slope(start: Point, end: Point, length_m: float):
    # Причины недоступности уклона описывает validate_input().
    if length_m <= 0:
        return None

    if start.axis is None or end.axis is None:
        return None

    return (end.axis - start.axis) / length_m * 1000

