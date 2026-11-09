from xml.etree import ElementTree as ET

from config import drawing_settings as settings
from core.calculations import calculate_point_levels, calculate_route_geometry
from config.drawing_settings import DEFAULT_FONT_SIZE_MM
from config.paths import TEMPLATES_DIR
from core.profile_grid import ProfileGrid
from core.profile_style import ProfileStyle
from core.sheet import Sheet
from core.drawing_scale import choose_scale
from core.pipe_drawing import pipe_line_count, pipe_leader, pipe_shelf_width
from core.formatting import render_template
from core.profile_labels import ProfileLabel
from core.label_geometry import rectangles_overlap, segment_crosses_rectangle, text_bounds


TEMPLATE_PATH = TEMPLATES_DIR / "profile.svg"


class ProfileDrawing:
    """Профиль A3: отметки и размещение в заданных масштабах."""

    def __init__(self, project, document, config, font_size=DEFAULT_FONT_SIZE_MM,
                 horizontal_scale=None,
                 vertical_scale=settings.PROFILE_VERTICAL_SCALE):
        """Готовит геометрию и лист профиля в заданных масштабах."""
        if (horizontal_scale is not None and horizontal_scale <= 0) or vertical_scale <= 0:
            raise ValueError("Масштабы профиля должны быть положительными.")
        self.project, self.config = project, config
        self.style = ProfileStyle(font_size)
        self.style.check_table()
        self.horizontal_scale, self.vertical_scale = horizontal_scale, vertical_scale
        self.mm_per_meter_y = 1000 / self.vertical_scale
        self.prepare_data()
        self.sheet = Sheet(document["designation"], project.object.name, document["title"])
        self.horizontal_scale = horizontal_scale or self.choose_horizontal_scale()
        self.mm_per_meter_x = 1000 / self.horizontal_scale
        self.datum_y = (self.sheet.height - settings.PROFILE_TITLE_BLOCK_OFFSET_MM
                        - settings.PROFILE_GRID_BOTTOM_GAP_MM - settings.PROFILE_GRID_HEIGHT_MM)
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
        self.two_lines = pipe_line_count(diameter, self.vertical_scale) == 2

    def choose_horizontal_scale(self):
        """Выбирает крупнейший масштаб из ряда, при котором вся длина помещается в поле."""
        available = (self.sheet.width - settings.PROFILE_FIELD_HORIZONTAL_MARGINS_MM
                     - settings.PROFILE_POINT_ORIGIN_MM - settings.PROFILE_GRID_RIGHT_PADDING_MM)
        return choose_scale((self.stations[-1],), (available,), settings.PROFILE_HORIZONTAL_SCALES,
                            settings.PROFILE_FIT_ERROR)

    def place_profile(self):
        """Прижимает низ трубы к таблице и возвращает начало пикетажа и условный горизонт."""
        width = settings.PROFILE_POINT_ORIGIN_MM + self.stations[-1] * self.mm_per_meter_x + settings.PROFILE_GRID_RIGHT_PADDING_MM
        if width > self.sheet.width - settings.PROFILE_FIELD_HORIZONTAL_MARGINS_MM:
            raise ValueError("Профиль не помещается на A3 при выбранном горизонтальном масштабе.")
        bottom = [value for value in self.bottom_levels if value is not None]
        if not bottom:
            raise ValueError("Нет отметок оси трубы для построения профиля.")
        datum = min(bottom) - settings.PROFILE_LOWEST_PIPE_GAP_MM / self.mm_per_meter_y
        left = settings.PROFILE_FRAME_LEFT_MM + (self.sheet.width - settings.PROFILE_FRAME_HORIZONTAL_MARGINS_MM - width) / 2
        return left + settings.PROFILE_POINT_ORIGIN_MM, datum

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

    def pipe_label_candidate(self, index, shelf_y, direction=1, side_offset=settings.PIPE_SHELF_SIDE_OFFSET_MM):
        """Возвращает полку над серединой участка и её прямоугольник на листе."""
        start, end = self.project.points[index:index + 2]
        if start.axis is None or end.axis is None:
            return None
        station = (self.stations[index] + self.stations[index + 1]) / 2
        upper = (start.axis + end.axis) / 2 + self.project.pipe.outer_diameter_mm / 2000
        target = (self.origin_x + station * self.mm_per_meter_x,
                  self.datum_y - (upper - self.datum_level) * self.mm_per_meter_y)
        shelf_x = target[0] + direction * side_offset
        label = pipe_leader(self.project.pipe, target, (shelf_x, shelf_y), direction)
        bounds = tuple(map(float, ET.fromstring(label).get("data-bounds").split()))
        return label, bounds

    def label_obstacles(self):
        """Возвращает подписи глубин, заголовок, землю и вертикали как препятствия полки."""
        grid = ProfileGrid(self)
        labels = grid.projection_labels() + grid.scale_obstacles()
        # Габариты учебной надписи заданы общими настройками шаблона листа.
        labels.append(ProfileLabel(settings.TRAINING_LABEL,
                      text_bounds(settings.TRAINING_LABEL, settings.SHEET_TRAINING_X_MM, settings.SHEET_TRAINING_Y_MM, settings.SHEET_TRAINING_FONT_MM, "middle"), None, "above"))
        ground, segments = [], []
        for index, point in enumerate(self.project.points):
            point_x = self.origin_x + self.stations[index] * self.mm_per_meter_x
            if point.ground is None:
                ground.append(None)
                continue
            point_y = self.datum_y - (point.ground - self.datum_level) * self.mm_per_meter_y
            ground.append((point_x, point_y))
            segments.append(((point_x, point_y), (point_x, self.datum_y)))
        segments.extend((start, end) for start, end in zip(ground, ground[1:]) if start and end)
        return labels, segments

    def shelf_fits(self, bounds, labels, segments):
        """Проверяет полку против рамки, заголовка, земли, вертикалей и глубин."""
        clearance = settings.PROFILE_SHELF_CLEARANCE_MM
        left, top, right, bottom = bounds
        expanded = left - clearance, top - clearance, right + clearance, bottom + clearance
        table_left = self.origin_x - settings.PROFILE_POINT_ORIGIN_MM
        table_right = self.origin_x + self.stations[-1] * self.mm_per_meter_x + settings.PROFILE_GRID_RIGHT_PADDING_MM
        return (left >= table_left and right <= table_right
                and top >= settings.PROFILE_TEXT_TOP_MM
                and not any(rectangles_overlap(expanded, label.bounds) for label in labels)
                and not any(segment_crosses_rectangle(start, end, expanded) for start, end in segments))

    def shelf_candidates(self, index):
        """Перебирает полки над землёй: по центру, справа и слева, затем выше."""
        ground = [point.ground for point in self.project.points[index:index + 2] if point.ground is not None]
        highest = max(ground) if ground else max(value for value in self.top_levels if value is not None)
        shelf_y = (self.datum_y - (highest - self.datum_level) * self.mm_per_meter_y
                   - settings.PROFILE_SHELF_CLEARANCE_MM - settings.PIPE_LABEL_FONT_SIZE_MM
                   - settings.PIPE_SHELF_TEXT_GAP_MM)
        while shelf_y - settings.PIPE_LABEL_FONT_SIZE_MM - settings.PIPE_SHELF_TEXT_GAP_MM >= settings.PROFILE_TEXT_TOP_MM:
            for direction in (1, -1):
                for offset in (settings.PIPE_SHELF_SIDE_OFFSET_MM,
                               settings.PIPE_SHELF_SIDE_OFFSET_MM + pipe_shelf_width(self.project.pipe)):
                    candidate = self.pipe_label_candidate(index, shelf_y, direction, offset)
                    if candidate is not None:
                        yield candidate
            shelf_y -= settings.PROFILE_SHELF_STEP_MM

    def draw_pipe_label(self):
        """Ищет свободную полку над землёй, перебирая участки от самого длинного."""
        labels, segments = self.label_obstacles()
        indices = sorted(range(len(self.sections)), key=lambda index: self.sections[index]["length_m"], reverse=True)
        for index in indices:
            for label, bounds in self.shelf_candidates(index):
                if self.shelf_fits(bounds, labels, segments):
                    return f'<g id="profile-pipe-label" data-placement="ok">{label}</g>'
        return '<g id="profile-pipe-label" data-placement="warning"/>'

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
            "pipe_label": self.draw_pipe_label() if self.two_lines else "",
            "reference": ProfileGrid(self).render(),
        })
        return self.sheet.render(drawing)
