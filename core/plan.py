from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from core.calculations import INPUT_PATH, calculate_route_geometry, load_project
from core.formatting import format_number, format_station
from core.sheet import Sheet


class PlanDrawing:
    """Построение плана: размещение трассы, геометрия и подписи."""

    def __init__(self, project):
        self.project = project
        self.scale = 1000
        self.mm_per_meter = 1000 / self.scale
        self.coordinates = self.place_points()
        self.sections = calculate_route_geometry(project.points)["sections"]

    def place_points(self):
        min_x = min(p.x for p in self.project.points)
        max_x = max(p.x for p in self.project.points)
        min_y = min(p.y for p in self.project.points)
        max_y = max(p.y for p in self.project.points)
        width = (max_x - min_x) * self.mm_per_meter
        height = (max_y - min_y) * self.mm_per_meter

        # Свободное поле над штампом: x=30..405, y=35..227 мм.
        if width > 375 or height > 192:
            raise ValueError(
                "Трасса не помещается на A3 при масштабе 1:1000. "
                "Требуется другой формат или масштаб."
            )

        left = 30 + (375 - width) / 2
        top = 35 + (192 - height) / 2
        coordinates = []
        for point in self.project.points:
            x = left + (point.x - min_x) * self.mm_per_meter
            y = top + (max_y - point.y) * self.mm_per_meter
            coordinates.append((x, y))
        return coordinates

    def draw_geometry(self):
        points = " ".join(f"{x},{y}" for x, y in self.coordinates)
        elements = [
            f'<g id="route-geometry" data-scale="{self.scale}">',
            f'<polyline id="route-line" points="{points}" fill="none" stroke="black" stroke-width="0.7"/>',
        ]
        for point, (x, y) in zip(self.project.points, self.coordinates):
            elements.append(
                f'<circle data-point-id={quoteattr(point.id)} cx="{x}" cy="{y}" r="1" '
                'fill="white" stroke="black" stroke-width="0.3"/>'
            )
        elements.append('</g>')
        return "\n".join(elements)

    def draw_point_labels(self):
        elements = []
        for i, (point, (x, y)) in enumerate(zip(self.project.points, self.coordinates)):
            station = 0.0 if i == 0 else self.sections[i - 1]["cumsum_dist_m"]
            # По краям листа подписи направлены внутрь свободного поля.
            label_x = x + 4 if x <= 217.5 else x - 4
            anchor = "start" if x <= 217.5 else "end"
            elements.append(
                f'<text data-kind="point-name" data-point-id={quoteattr(point.id)} '
                f'x="{label_x}" y="{y - 10}" text-anchor="{anchor}">{escape(point.id)}</text>'
            )
            elements.append(
                f'<text data-kind="station" data-point-id={quoteattr(point.id)} '
                f'x="{label_x}" y="{y - 5}" text-anchor="{anchor}">{format_station(station)}</text>'
            )
        return "\n".join(elements)

    def draw_lengths(self):
        elements = []
        for i, section in enumerate(self.sections):
            x1, y1 = self.coordinates[i]
            x2, y2 = self.coordinates[i + 1]
            length_mm = section["length_m"] * self.mm_per_meter
            # Сдвиг от середины участка на 5 мм по перпендикуляру к линии.
            label_x = (x1 + x2) / 2 - (y2 - y1) / length_mm * 5
            label_y = (y1 + y2) / 2 + (x2 - x1) / length_mm * 5 + 1.2
            elements.append(
                f'<text data-kind="length" data-start-id={quoteattr(section["start_id"])} '
                f'data-end-id={quoteattr(section["end_id"])} x="{label_x}" y="{label_y}" '
                f'text-anchor="middle">{format_number(section["length_m"])}</text>'
            )
        return "\n".join(elements)

    def render(self):
        svg = Sheet(
            self.project.object.project_code + "-НВ", self.project.object.name,
            f"План сетей водоснабжения (1:{self.scale})", 2, "",
        ).render()
        # REQ-001, REQ-027, REQ-073, REQ-096: округляется только вывод подписей.
        labels = '<g id="route-labels" font-family="Arial, sans-serif" font-size="3.5" fill="black">'
        elements = [
            self.draw_geometry(), labels,
            self.draw_point_labels(), self.draw_lengths(), '</g>',
        ]
        return svg.replace("</svg>", "\n".join(elements) + "\n</svg>")


def create_plan(input_file=INPUT_PATH, output_file=INPUT_PATH.parent.parent / "output" / "plan.svg"):
    project, problems = load_project(Path(input_file))
    if project is None or any(p["blocks_length"] for p in problems):
        return {"status": "error", "problems": problems}

    try:
        drawing = PlanDrawing(project)
        svg = drawing.render()
    except ValueError as error:
        return {"status": "error", "message": str(error)}

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(svg, encoding="utf-8")
    return {"status": "ok", "files": {"svg": str(output_file)}, "scale": drawing.scale, "problems": problems}


if __name__ == "__main__":
    print(create_plan())
