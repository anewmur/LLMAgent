from xml.sax.saxutils import escape, quoteattr

from core import drawing_settings as settings
from core.formatting import format_number, format_pipe_value, format_station
from core.paths import TEMPLATES_DIR
from core.formatting import render_template


TEMPLATE_PATH = TEMPLATES_DIR / "profile_grid.svg"
# Привязки боковика и точек к шаблону profile_grid.svg, мм листа.
SIDEBAR_WIDTH = settings.PROFILE_SIDEBAR_WIDTH_MM
POINT_ORIGIN = SIDEBAR_WIDTH + 6
LABEL_OFFSET = 1.5
# Высоты строк и координаты их центров по шаблону profile_grid.svg, мм листа.
BOTTOM_LEVEL_Y = 7.5
GROUND_LEVEL_Y = 22.5
NATURAL_GROUND_Y = 37.5
SLOPE_VALUE_Y = 81
SLOPE_ROW_TOP = settings.PROFILE_BASE_ROW_BOTTOM_MM
SLOPE_ROW_BOTTOM = settings.PROFILE_SLOPE_ROW_BOTTOM_MM
SLOPE_LINE_Y = (SLOPE_ROW_TOP + SLOPE_ROW_BOTTOM) / 2
SECTION_LENGTH_Y = 96
DISTANCE_Y = 107
POINT_NAME_Y = 121
STATION_Y = 141
LEVEL_ROWS_BOTTOM = settings.PROFILE_NATURAL_GROUND_ROW_BOTTOM_MM
DISTANCE_ROW_TOP = SLOPE_ROW_BOTTOM
GRID_HEIGHT = settings.PROFILE_GRID_HEIGHT_MM


class ProfileGrid:
    """Сетка формы 2 и привязки значений к тем же пикетам, что у профиля."""

    def __init__(self, drawing):
        """Готовит абсциссы точек сетки и общую нумерацию отводов."""
        self.drawing = drawing
        self.project = drawing.project
        self.point_x = [POINT_ORIGIN + station * drawing.mm_per_meter_x for station in drawing.stations]
        self.bend_names = self.project.bend_names()

    def vertical_text(self, value, point_x, row_y, kind, point_id):
        """Возвращает SVG вертикальной подписи в строке сетки."""
        return (
            f'<text data-kind="{kind}" data-point-id={quoteattr(point_id)} '
            f'transform="translate({point_x - LABEL_OFFSET} {row_y}) rotate(-90)" text-anchor="middle">'
            f'{escape(str(value))}</text>'
        )

    def draw_values(self):
        """Возвращает SVG значений у точек и вертикальных линий сетки."""
        elements = []
        for index, point in enumerate(self.project.points):
            name = point.id
            if point.id in self.bend_names:
                name += " / " + self.bend_names[point.id]
            values = [
                (format_number(self.drawing.bottom_levels[index]), BOTTOM_LEVEL_Y, "bottom-level"),
                (format_number(point.ground), GROUND_LEVEL_Y, "ground-level"),
                ("—", NATURAL_GROUND_Y, "natural-ground"), (name, POINT_NAME_Y, "point-name"),
                (format_station(self.drawing.stations[index]), STATION_Y, "station"),
            ]
            for value, row_y, kind in values:
                elements.append(self.vertical_text(value, self.point_x[index], row_y, kind, point.id))
            elements.append(f'<path d="M {self.point_x[index]},0 V {LEVEL_ROWS_BOTTOM} '
                            f'M {self.point_x[index]},{DISTANCE_ROW_TOP} V {GRID_HEIGHT}" '
                            f'fill="none" stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')
        return "\n".join(elements)

    def draw_slope(self, start_x, end_x, slope):
        """Возвращает SVG линии направления уклона или пустую строку без отметок."""
        if slope is None:
            return ""
        start_y = end_y = SLOPE_LINE_Y
        if slope > 0:
            start_y, end_y = SLOPE_ROW_BOTTOM, SLOPE_ROW_TOP
        elif slope < 0:
            start_y, end_y = SLOPE_ROW_TOP, SLOPE_ROW_BOTTOM
        return (f'<path data-kind="slope-line" d="M {start_x},{start_y} L {end_x},{end_y}" '
                f'fill="none" stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')

    def draw_sections(self):
        """Возвращает SVG уклонов, длин и расстояний между точками."""
        elements = []
        for index, section in enumerate(self.drawing.sections):
            start_x, end_x = self.point_x[index:index + 2]
            middle = (start_x + end_x) / 2
            slope = section["slope_per_mille"]
            if index:
                elements.append(f'<line data-kind="slope-divider" x1="{start_x}" x2="{start_x}" '
                                f'y1="{SLOPE_ROW_TOP}" y2="{SLOPE_ROW_BOTTOM}" '
                                f'stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')
            elements.append(self.draw_slope(start_x, end_x, slope))
            for value, row_y, kind in [(format_number(slope), SLOPE_VALUE_Y, "slope"),
                                   (format_number(section["length_m"]), SECTION_LENGTH_Y, "slope-length"),
                                   (format_number(section["length_m"]), DISTANCE_Y, "distance")]:
                elements.append(f'<text data-kind="{kind}" data-start-id={quoteattr(section["start_id"])} '
                                f'data-end-id={quoteattr(section["end_id"])} x="{middle}" y="{row_y}" '
                                f'text-anchor="middle">{value}</text>')
        return "\n".join(elements)

    def pipe_labels(self):
        """Возвращает экранированные наименование и размеры трубы для шаблона."""
        pipe = self.project.pipe
        size = f"{format_pipe_value(pipe.outer_diameter_mm)}×{format_pipe_value(pipe.wall_mm)}"
        sdr = format_pipe_value(pipe.sdr)
        return {"pipe_name": escape(f"{settings.NETWORK_CODE} — Труба {pipe.material}"),
                "pipe_size": escape(f"SDR {sdr} ⌀{size}")}

    def draw_projections(self):
        """Возвращает SVG проекций точек к сетке и подписей глубины."""
        drawing = self.drawing
        elements = [f'<g id="profile-projections" font-family="{settings.FONT_FAMILY}" '
                    f'font-size="{drawing.style.base_size}">']
        for index, (point, station) in enumerate(zip(self.project.points, drawing.stations)):
            level = point.ground if point.ground is not None else drawing.bottom_levels[index]
            if level is None:
                continue
            sheet_x = drawing.origin_x + station * drawing.mm_per_meter_x
            sheet_y = drawing.datum_y - (level - drawing.datum_level) * drawing.mm_per_meter_y
            elements.append(f'<path data-point-id={quoteattr(point.id)} d="M {sheet_x},{sheet_y} V {drawing.datum_y}" '
                            f'stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')
            depth = drawing.levels[index]["depth_to_bottom_m"]
            elements.append(f'<text data-kind="depth" data-point-id={quoteattr(point.id)} '
                            f'transform="translate({sheet_x - LABEL_OFFSET} {sheet_y - settings.PROFILE_DEPTH_LABEL_OFFSET_MM}) '
                            'rotate(-90)" text-anchor="middle">'
                            f'{format_number(depth)}</text>')
        elements.append('</g>')
        return "\n".join(elements)

    def render(self):
        """Возвращает SVG проекций и сетки с подставленными расчётными значениями."""
        drawing = self.drawing
        grid = render_template(TEMPLATE_PATH, {
            "left": drawing.origin_x - POINT_ORIGIN,
            "top": drawing.datum_y,
            "width": self.point_x[-1] + settings.PROFILE_GRID_RIGHT_PADDING_MM,
            "middle": (POINT_ORIGIN + self.point_x[-1]) / 2,
            "values": self.draw_values(),
            "sections": self.draw_sections(),
            **self.pipe_labels(),
            "horizontal_scale": drawing.horizontal_scale,
            "vertical_scale": drawing.vertical_scale,
            "datum": format_number(drawing.datum_level),
            "font_size": drawing.style.base_size,
            "title_size": drawing.style.title_size,
            "font_family": settings.FONT_FAMILY,
            "grid_line_width": settings.PROFILE_GRID_LINE_WIDTH_MM,
            "sidebar_width": SIDEBAR_WIDTH,
            "grid_height": GRID_HEIGHT,
            "bottom_level_row_bottom": settings.PROFILE_BOTTOM_LEVEL_ROW_BOTTOM_MM,
            "ground_row_bottom": settings.PROFILE_GROUND_ROW_BOTTOM_MM,
            "natural_ground_row_bottom": LEVEL_ROWS_BOTTOM,
            "pipe_row_bottom": settings.PROFILE_PIPE_ROW_BOTTOM_MM,
            "base_row_bottom": SLOPE_ROW_TOP,
            "slope_row_bottom": SLOPE_ROW_BOTTOM,
            "distance_row_bottom": settings.PROFILE_DISTANCE_ROW_BOTTOM_MM,
            "point_row_bottom": settings.PROFILE_POINT_ROW_BOTTOM_MM,
        })
        return self.draw_projections() + "\n" + grid
