from math import floor
from pathlib import Path

from core.calculations import INPUT_PATH, calculate_point_levels, calculate_route_geometry, load_project
from core.formatting import format_number
from core.sheet import Sheet


class ProfileDrawing:
    """Геометрия профиля по пикетам и высотным отметкам, без сетки."""

    def __init__(self, project):
        self.horizontal_scale = 1000
        self.vertical_scale = 100
        self.mm_per_meter_x = 1000 / self.horizontal_scale
        self.mm_per_meter_y = 1000 / self.vertical_scale
        geometry = calculate_route_geometry(project.points)
        self.stations = [0.0] + [s["cumsum_dist_m"] for s in geometry["sections"]]
        levels = calculate_point_levels(project.points, project.pipe.outer_diameter_mm)
        self.ground_levels = [point.ground for point in project.points]
        self.bottom_levels = [point["bottom_m"] for point in levels]
        self.sheet = Sheet(
            project.object.project_code + "-НВ", project.object.name,
            "Профиль сетей водоснабжения", 3, "", paper="A2",
        )
        self.datum_y = 210
        self.origin_x, self.datum_level = self.place_profile()

    def place_profile(self):
        # Поля 45 мм и боковик будущей сетки 70 мм; график выше y=210.
        available_width = self.sheet.width - 115
        width = self.stations[-1] * self.mm_per_meter_x
        levels = [v for v in self.ground_levels + self.bottom_levels if v is not None]
        if not levels:
            raise ValueError("Нет отметок земли и оси трубы для построения профиля.")
        datum_level = floor(min(levels)) - 1
        height = (max(levels) - datum_level) * self.mm_per_meter_y
        if width > available_width or height > self.datum_y - 55:
            raise ValueError(
                "Профиль не помещается на A2 при масштабах 1:1000 и 1:100. "
                "Требуется другой формат или масштаб."
            )
        return 100 + (available_width - width) / 2, datum_level

    def draw_line(self, levels, line_id, thickness):
        commands = []
        connected = False
        for station, level in zip(self.stations, levels):
            if level is None:
                connected = False
                continue
            x = self.origin_x + station * self.mm_per_meter_x
            y = self.datum_y - (level - self.datum_level) * self.mm_per_meter_y
            commands.append(f'{"L" if connected else "M"} {x},{y}')
            connected = True
        return (
            f'<path id="{line_id}" d="{" ".join(commands)}" fill="none" '
            f'stroke="black" stroke-width="{thickness}"/>'
        )

    def draw_reference(self):
        left = self.origin_x - 70
        right = self.origin_x + self.stations[-1] * self.mm_per_meter_x
        return f'''<g id="profile-reference" font-family="Arial, sans-serif" font-size="3.5">
  <path d="M {self.origin_x},{self.datum_y} H {right}" stroke="black" stroke-width="0.3"/>
  <path d="M {left},174 h 10" stroke="black" stroke-width="0.3"/>
  <text x="{left + 14}" y="175.2">Земля</text>
  <path d="M {left},182 h 10" stroke="black" stroke-width="0.7"/>
  <text x="{left + 14}" y="183.2">Низ трубы</text>
  <text x="{left}" y="193">М 1:{self.horizontal_scale} по горизонтали</text>
  <text x="{left}" y="200">М 1:{self.vertical_scale} по вертикали</text>
  <text x="{left}" y="{self.datum_y}">УГ {format_number(self.datum_level)}</text>
</g>'''

    def render(self):
        # REQ-030, REQ-097: низ трубы из расчёта, разрывы при пропусках.
        elements = [
            f'<g id="profile-geometry" data-datum-m="{self.datum_level}" '
            f'data-horizontal-scale="{self.horizontal_scale}" data-vertical-scale="{self.vertical_scale}">',
            self.draw_line(self.ground_levels, "ground-line", "0.3"),
            self.draw_line(self.bottom_levels, "pipe-bottom-line", "0.7"),
            '</g>', self.draw_reference(),
        ]
        return self.sheet.render().replace("</svg>", "\n".join(elements) + "\n</svg>")


def create_profile(input_file=INPUT_PATH, output_file=INPUT_PATH.parent.parent / "output" / "profile.svg"):
    project, problems = load_project(Path(input_file))
    if project is None or any(p["blocks_length"] for p in problems):
        return {"status": "error", "problems": problems}
    try:
        drawing = ProfileDrawing(project)
        svg = drawing.render()
    except ValueError as error:
        return {"status": "error", "message": str(error), "problems": problems}
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(svg, encoding="utf-8")
    return {
        "status": "ok", "files": {"svg": str(output_file)}, "problems": problems,
        "horizontal_scale": drawing.horizontal_scale, "vertical_scale": drawing.vertical_scale,
    }


if __name__ == "__main__":
    print(create_profile())
