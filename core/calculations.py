import json
from decimal import Decimal
from collections import Counter
from pathlib import Path
from core.models import Point, Project
from core.validate import validate_input


def calculate_route_geometry(points: list[Point]):
    sections = []
    total = 0.0

    for start, end in zip(points, points[1:]):
        delta_x = end.x - start.x
        delta_y = end.y - start.y
        length = (delta_x ** 2 + delta_y ** 2) ** 0.5

        start_station = total
        total += length

        sections.append({
            "start_id": start.id,
            "end_id": end.id,
            "length_m": length,
            "start_station_m": start_station,
            "cumsum_dist_m": total,
            "slope_per_mille": calculate_slope(start, end, length),
        })

    return {
        "length_m": total,
        "sections": sections,
    }


def load_project(input_file):
    """Читает начальный JSON и возвращает проект с результатами проверки."""
    data = json.loads(Path(input_file).read_text(encoding="utf-8"))
    return validate_input(data)


def calculate_route_length(project: Project):
    """Возвращает длину и участки готового проверенного проекта."""
    return calculate_route_geometry(project.points)

def calculate_pipe_levels(project: Project):
    """Возвращает отметки и глубины готового проверенного проекта."""
    return {
        "point_levels": calculate_point_levels(
            project.points, project.pipe.outer_diameter_mm
        ),
    }


def calculate_material_quantities(project: Project):
    """Возвращает количества материалов готового проверенного проекта."""
    geometry = calculate_route_geometry(project.points)
    bend_counts = Counter(bend.angle_deg for bend in project.bends)
    return {
        "pipe": {
            "material": project.pipe.material,
            "sdr": project.pipe.sdr,
            "outer_diameter_mm": project.pipe.outer_diameter_mm,
            "wall_mm": project.pipe.wall_mm,
            "standard": project.pipe.standard,
            "quantity_m": geometry["length_m"],
        },
        "bends": [
            {"angle_deg": angle, "quantity_pcs": count}
            for angle, count in sorted(bend_counts.items())
        ],
    }


def calculate_point_levels(points: list[Point], outer_diameter_mm: float):
    # расчёт высотных значений в каждой точке: отметки наружного низа трубы и глубины от земли до этого низа.
    radius_m = Decimal(str(outer_diameter_mm)) / 2000
    levels = []

    for point in points:
        bottom = None
        depth = None

        if point.axis is not None:
            # Сохраняем десятичную точность исходных отметок до округления вывода.
            bottom_decimal = Decimal(str(point.axis)) - radius_m
            bottom = float(bottom_decimal)
            if point.ground is not None:
                depth = float(Decimal(str(point.ground)) - bottom_decimal)

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

    difference = Decimal(str(end.axis)) - Decimal(str(start.axis))
    return float(difference / Decimal(str(length_m)) * 1000)

