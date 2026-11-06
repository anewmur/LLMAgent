from pathlib import Path
from math import atan2, degrees
from xml.sax.saxutils import escape, quoteattr

from core.calculations import INPUT_PATH, calculate_route_geometry, load_project
from core.formatting import format_number, format_station
from core.sheet import Sheet


LEGEND_PATH = Path(__file__).resolve().parent.parent / "templates" / "plan_legend.svg"


class PlanDrawing:
    """Построение плана: трасса, подписи, обозначения и легенда."""

    def __init__(self, project):
        self.project = project
        self.scale = 1000
        self.mm_per_meter = 1000 / self.scale
        self.coordinates = self.place_points()
        self.sections = calculate_route_geometry(project.points)["sections"]
        self.bends = {bend.at: bend for bend in project.bends}
        bend_ids = [point.id for point in project.points if point.id in self.bends]
        self.bend_names = {pid: f"УП{i}" for i, pid in enumerate(bend_ids, 1)}

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
        # REQ-014, REQ-086: проектируемая подземная труба, без знаков колодцев.
        return "\n".join([
            f'<g id="route-geometry" data-scale="{self.scale}">',
            f'<polyline id="route-line" points="{points}" fill="none" stroke="black" '
            'stroke-width="0.7" stroke-dasharray="6 2" stroke-linejoin="miter"/>',
            '</g>',
        ])

    def point_title(self, point_id):
        title = point_id
        if point_id in self.bends:
            title += f" / {self.bend_names[point_id]}"
            # ГОСТ 21.704, п. 5.1.2: числовое значение 90° не указывают.
            angle_minutes = round(self.bends[point_id].angle_deg * 60)
            if angle_minutes != 90 * 60:
                whole, minutes = divmod(angle_minutes, 60)
                title += f" ({whole}°{minutes:02d}′)"
        return escape(title)

    def point_label_position(self, index):
        x, y = self.coordinates[index]
        neighbors = self.coordinates[max(0, index - 1):index + 2]
        upper = [(px, py) for px, py in neighbors if py < y]
        # Подпись выше точки уводим от участка, направленного вверх.
        left = upper[0][0] >= x if upper else x > 217.5
        return (x - 4, "end") if left else (x + 4, "start")

    def draw_point_labels(self):
        elements = []
        for i, (point, (x, y)) in enumerate(zip(self.project.points, self.coordinates)):
            station = 0.0 if i == 0 else self.sections[i - 1]["cumsum_dist_m"]
            label_x, anchor = self.point_label_position(i)
            elements.append(
                f'<text data-kind="point-name" data-point-id={quoteattr(point.id)} '
                f'x="{label_x}" y="{y - 10}" text-anchor="{anchor}">{self.point_title(point.id)}</text>'
            )
            elements.append(
                f'<text data-kind="station" data-point-id={quoteattr(point.id)} '
                f'x="{label_x}" y="{y - 5}" text-anchor="{anchor}">{format_station(station)}</text>'
            )
        return "\n".join(elements)

    def draw_pipe_label(self):
        """REQ-011, REQ-017: одна подпись трубы вдоль самого длинного участка."""
        index = max(range(len(self.sections)), key=lambda i: self.sections[i]["length_m"])
        x1, y1 = self.coordinates[index]
        x2, y2 = self.coordinates[index + 1]
        angle = degrees(atan2(y2 - y1, x2 - x1))
        if angle > 90 or angle < -90:
            angle += -180 if angle > 90 else 180
        pipe = self.project.pipe
        diameter = f"{pipe.outer_diameter_mm:g}".replace(".", ",")
        wall = f"{pipe.wall_mm:g}".replace(".", ",")
        sdr = f"{pipe.sdr:g}".replace(".", ",")
        text = f"В1 — {pipe.material} SDR {sdr} ⌀{diameter}×{wall}"
        return (
            f'<text data-kind="pipe-label" text-anchor="middle" x="0" y="-8" '
            f'transform="translate({(x1 + x2) / 2:g} {(y1 + y2) / 2:g}) rotate({angle:g})">'
            f'{escape(text)}</text>'
        )

    def draw_legend(self):
        return LEGEND_PATH.read_text(encoding="utf-8")

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
            self.draw_point_labels(), self.draw_lengths(), self.draw_pipe_label(), '</g>',
            self.draw_legend(),
        ]
        return svg.replace("</svg>", "\n".join(elements) + "\n</svg>")


def create_plan(input_file=INPUT_PATH, output_file=INPUT_PATH.parent.parent / "output" / "plan.svg"):
    project, problems = load_project(Path(input_file))
    if project is None or any(p["blocks_length"] for p in problems):
        return {"status": "error", "problems": problems}
    bend_ids = {bend.at for bend in project.bends}
    if any(p["level"] == "error" and p["where"] in bend_ids for p in problems):
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
