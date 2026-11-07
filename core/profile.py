from core import drawing_settings as settings
from core.calculations import calculate_point_levels, calculate_route_geometry
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.paths import TEMPLATES_DIR
from core.profile_grid import GRID_HEIGHT, POINT_ORIGIN, ProfileGrid
from core.profile_style import ProfileStyle
from core.sheet import Sheet
from core.templates import render_template


TEMPLATE_PATH = TEMPLATES_DIR / "profile.svg"


class ProfileDrawing:
    """Профиль A3: отметки и размещение в заданных масштабах."""

    def __init__(self, project, document, font_size=DEFAULT_FONT_SIZE_MM,
                 horizontal_scale=settings.PROFILE_HORIZONTAL_SCALE,
                 vertical_scale=settings.PROFILE_VERTICAL_SCALE):
        """Готовит геометрию и лист профиля в заданных масштабах."""
        if horizontal_scale <= 0 or vertical_scale <= 0:
            raise ValueError("Масштабы профиля должны быть положительными.")
        self.project = project
        self.style = ProfileStyle(font_size)
        self.style.check_table()
        self.horizontal_scale, self.vertical_scale = horizontal_scale, vertical_scale
        self.mm_per_meter_x = 1000 / self.horizontal_scale
        self.mm_per_meter_y = 1000 / self.vertical_scale
        self.prepare_data()
        self.sheet = Sheet(document["designation"], project.object.name, document["title"])
        self.datum_y = (self.sheet.height - settings.PROFILE_TITLE_BLOCK_OFFSET_MM
                        - settings.PROFILE_GRID_BOTTOM_GAP_MM - GRID_HEIGHT)
        self.origin_x, self.datum_level = self.place_profile()

    def prepare_data(self):
        """Вычисляет участки, пикеты и отметки для линий профиля."""
        geometry = calculate_route_geometry(self.project.points)
        self.sections = geometry["sections"]
        self.stations = [0.0] + [section["cumsum_dist_m"] for section in self.sections]
        diameter = self.project.pipe.outer_diameter_mm
        self.levels = calculate_point_levels(self.project.points, diameter)
        self.ground_levels = [point.ground for point in self.project.points]
        self.bottom_levels = [level["bottom_m"] for level in self.levels]
        self.top_levels = [None if value is None else value + diameter / 1000 for value in self.bottom_levels]
        self.two_lines = diameter / self.vertical_scale >= settings.PROFILE_TWO_LINE_THRESHOLD_MM

    def place_profile(self):
        """Возвращает начало пикетажа и отметку условного горизонта при размещении в поле."""
        width = POINT_ORIGIN + self.stations[-1] * self.mm_per_meter_x + settings.PROFILE_GRID_RIGHT_PADDING_MM
        visible = self.ground_levels + self.bottom_levels
        if self.two_lines:
            visible += self.top_levels
        levels = [value for value in visible if value is not None]
        if not levels:
            raise ValueError("Нет отметок земли и оси трубы для построения профиля.")
        height = (max(levels) - min(levels)) * self.mm_per_meter_y
        available_height = self.datum_y - settings.PROFILE_FRAME_TOP_MM - 2 * settings.PROFILE_VERTICAL_MARGIN_MM
        if width > self.sheet.width - settings.PROFILE_FIELD_HORIZONTAL_MARGINS_MM or height > available_height:
            raise ValueError(f"Профиль не помещается на A3 при масштабах 1:{self.horizontal_scale} и 1:{self.vertical_scale}. "
                             "Нужны другой формат или деление на листы; автоподбор не реализован.")
        center_y = (settings.PROFILE_FRAME_TOP_MM + self.datum_y) / 2
        center_level = (min(levels) + max(levels)) / 2
        datum = center_level - (self.datum_y - center_y) / self.mm_per_meter_y
        left = settings.PROFILE_FRAME_LEFT_MM + (self.sheet.width - settings.PROFILE_FRAME_HORIZONTAL_MARGINS_MM - width) / 2
        return left + POINT_ORIGIN, datum

    def path_data(self, levels):
        """Возвращает SVG-команды линии, оставляя разрывы на пропущенных отметках."""
        commands, connected = [], False
        for station, level in zip(self.stations, levels):
            if level is None:
                connected = False
                continue
            sheet_x = self.origin_x + station * self.mm_per_meter_x
            sheet_y = self.datum_y - (level - self.datum_level) * self.mm_per_meter_y
            commands.append(f'{"L" if connected else "M"} {sheet_x},{sheet_y}')
            connected = True
        return " ".join(commands)

    def render(self):
        """Возвращает SVG-лист с линиями, проекциями и сеткой профиля."""
        top = ""
        if self.two_lines:
            top = (f'<path id="pipe-top-line" d="{self.path_data(self.top_levels)}" '
                   f'stroke-width="{settings.PROFILE_PIPE_LINE_WIDTH_MM}"/>')
        drawing = render_template(TEMPLATE_PATH, {
            "datum": self.datum_level,
            "font_size": self.style.base_size,
            "font_family": settings.FONT_FAMILY,
            "pipe_line_width": settings.PROFILE_PIPE_LINE_WIDTH_MM,
            "horizontal_scale": self.horizontal_scale,
            "vertical_scale": self.vertical_scale,
            "ground": self.path_data(self.ground_levels),
            "bottom": self.path_data(self.bottom_levels),
            "top": top,
            "reference": ProfileGrid(self).render(),
        })
        return self.sheet.render(drawing)
