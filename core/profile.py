from pathlib import Path
from string import Template
from xml.etree import ElementTree as ET

from core.calculations import INPUT_PATH, calculate_point_levels, calculate_route_geometry, load_project
from core.profile_grid import GRID_HEIGHT, POINT_ORIGIN, ProfileGrid
from core.profile_style import ProfileStyle
from core.sheet import Sheet, svg_to_pdf


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "profile.svg"
OUTPUT_PATH = INPUT_PATH.parent.parent / "tmp" / "profile.svg"
FRAME_TOP = 5
PROFILE_MARGIN = 10


class ProfileDrawing:
    """Профиль A3: отметки и размещение в заданных масштабах."""

    def __init__(self, project, font_size=3.5):
        self.project = project
        self.style = ProfileStyle(font_size)
        self.style.check_table()
        self.horizontal_scale, self.vertical_scale = 2000, 100
        self.mm_per_meter_x = 1000 / self.horizontal_scale
        self.mm_per_meter_y = 1000 / self.vertical_scale
        self.prepare_data()
        self.sheet = Sheet(project.object.project_code + "-НВ", project.object.name,
                           "Профиль В1", 3, "")
        self.datum_y = self.sheet.height - 60 - 5 - GRID_HEIGHT
        self.origin_x, self.datum_level = self.place_profile()

    def prepare_data(self):
        geometry = calculate_route_geometry(self.project.points)
        self.sections = geometry["sections"]
        self.stations = [0.0] + [s["cumsum_dist_m"] for s in self.sections]
        diameter = self.project.pipe.outer_diameter_mm
        self.levels = calculate_point_levels(self.project.points, diameter)
        self.ground_levels = [p.ground for p in self.project.points]
        self.bottom_levels = [p["bottom_m"] for p in self.levels]
        self.top_levels = [None if v is None else v + diameter / 1000 for v in self.bottom_levels]
        self.two_lines = diameter / self.vertical_scale >= 2

    def place_profile(self):
        width = POINT_ORIGIN + self.stations[-1] * self.mm_per_meter_x + 2
        visible = self.ground_levels + self.bottom_levels
        if self.two_lines:
            visible += self.top_levels
        levels = [v for v in visible if v is not None]
        if not levels:
            raise ValueError("Нет отметок земли и оси трубы для построения профиля.")
        height = (max(levels) - min(levels)) * self.mm_per_meter_y
        available_height = self.datum_y - FRAME_TOP - 2 * PROFILE_MARGIN
        if width > self.sheet.width - 35 or height > available_height:
            raise ValueError("Профиль не помещается на A3 при масштабах 1:2000 и 1:100. "
                             "Нужны другой формат или деление на листы; автоподбор не реализован.")
        center_y = (FRAME_TOP + self.datum_y) / 2
        center_level = (min(levels) + max(levels)) / 2
        datum = center_level - (self.datum_y - center_y) / self.mm_per_meter_y
        left = 20 + (self.sheet.width - 25 - width) / 2
        return left + POINT_ORIGIN, datum

    def path_data(self, levels):
        commands, connected = [], False
        for station, level in zip(self.stations, levels):
            if level is None:
                connected = False
                continue
            x = self.origin_x + station * self.mm_per_meter_x
            y = self.datum_y - (level - self.datum_level) * self.mm_per_meter_y
            commands.append(f'{"L" if connected else "M"} {x},{y}')
            connected = True
        return " ".join(commands)

    def render(self):
        top = ""
        if self.two_lines:
            top = f'<path id="pipe-top-line" d="{self.path_data(self.top_levels)}" stroke-width="1.0"/>'
        drawing = Template(TEMPLATE_PATH.read_text(encoding="utf-8")).safe_substitute(
            datum=self.datum_level, font_size=self.style.base_size,
            ground=self.path_data(self.ground_levels), bottom=self.path_data(self.bottom_levels),
            top=top, reference=ProfileGrid(self).render(),
        )
        return self.sheet.render().replace("</svg>", drawing + "\n</svg>")


class ProfileExport:
    """Запись профиля и изменение шрифта без правки исходного JSON."""

    def __init__(self, input_file=INPUT_PATH, output_file=OUTPUT_PATH):
        self.input_file, self.output_file = Path(input_file), Path(output_file)

    def create(self, font_size=3.5, pdf=False):
        project, problems = load_project(self.input_file)
        if project is None or any(p["blocks_length"] for p in problems):
            return {"status": "error", "problems": problems}
        try:
            drawing = ProfileDrawing(project, font_size)
            svg = drawing.render()
            self.output_file.parent.mkdir(parents=True, exist_ok=True)
            self.output_file.write_text(svg, encoding="utf-8")
            files = {"svg": str(self.output_file)}
            if pdf:
                pdf_path = self.output_file.with_suffix(".pdf")
                svg_to_pdf(self.output_file, pdf_path)
                files["pdf"] = str(pdf_path)
            return {"status": "ok", "files": files, "problems": problems,
                    "horizontal_scale": 2000, "vertical_scale": 100, "base_font_size": font_size}
        except (OSError, ValueError) as error:
            return {"status": "error", "message": str(error), "problems": problems}

    def change_font(self, direction):
        try:
            size = 3.5
            if self.output_file.exists():
                root = ET.parse(self.output_file).getroot()
                group = root.find("{http://www.w3.org/2000/svg}g[@id='profile-geometry']")
                size = float(group.get("data-font-size", "3.5"))
            return self.create(ProfileStyle.font_step(size, direction), pdf=True)
        except (OSError, ValueError, AttributeError, ET.ParseError) as error:
            return {"status": "error", "message": str(error)}


def create_profile(input_file=INPUT_PATH, output_file=OUTPUT_PATH, font_size=3.5):
    return ProfileExport(input_file, output_file).create(font_size)


if __name__ == "__main__":
    print(ProfileExport().create(pdf=True))
