from xml.sax.saxutils import escape, quoteattr
from html import unescape
from dataclasses import dataclass

from config import drawing_settings as settings
from core.formatting import format_number, format_pipe_value, format_station, format_slope, render_template
from config.paths import TEMPLATES_DIR
from core.label_geometry import labels_too_close, text_bounds
from core.tables import text_width
from core.profile_labels import ProfileLabel


TEMPLATE_PATH = TEMPLATES_DIR / "profile_grid.svg"
# Привязки боковика и точек к шаблону profile_grid.svg, мм листа.
# Высоты строк и координаты их центров по шаблону profile_grid.svg, мм листа.
SLOPE_LINE_Y = (settings.PROFILE_BASE_ROW_BOTTOM_MM + settings.PROFILE_SLOPE_ROW_BOTTOM_MM) / 2
STATION_Y = (settings.PROFILE_POINT_ROW_BOTTOM_MM + settings.PROFILE_GRID_HEIGHT_MM) / 2


@dataclass(frozen=True)
class Projection:
    """Положение проекции и подписи глубины, мм листа."""
    name: str
    left: float
    top: float
    depth: str
    baseline: float
    bounds: tuple
    fits: bool


class ProfileGrid:
    """Сетка формы 2 и привязки значений к тем же пикетам, что у профиля."""

    def __init__(self, drawing):
        """Готовит абсциссы точек сетки и общую нумерацию отводов."""
        self.drawing = drawing
        self.project = drawing.project
        self.point_x = [settings.PROFILE_POINT_ORIGIN_MM + station * drawing.mm_per_meter_x for station in drawing.stations]
        self.bend_names = self.project.bend_names()

    def cell_text(self, value, left, baseline, kind, cell, anchor="middle", attributes="", transform=""):
        """Возвращает текст с границами его клетки для независимой проверки SVG."""
        return render_template(TEMPLATES_DIR / "profile_text.svg", {
            "value": escape(str(value)), "left": left, "baseline": baseline, "kind": kind,
            "cell": " ".join(map(str, cell)), "anchor": anchor, "attributes": attributes,
            "transform": transform,
        })

    def vertical_text(self, value, index, row_y, kind, row_top, row_bottom):
        """Располагает вертикальное число в области ближайшей точки, возвращает SVG."""
        point_x = self.point_x[index]
        cell_left = (self.point_x[index - 1] + point_x) / 2 if index else settings.PROFILE_SIDEBAR_WIDTH_MM
        cell_right = ((point_x + self.point_x[index + 1]) / 2 if index + 1 < len(self.point_x)
                      else point_x + settings.PROFILE_GRID_RIGHT_PADDING_MM)
        padding = settings.PROFILE_CELL_PADDING_MM
        label_x = max(cell_left + self.drawing.style.base_size + padding,
                      min(point_x - settings.PROFILE_LABEL_OFFSET_MM, cell_right - padding))
        cell = (cell_left, row_top, cell_right, row_bottom)
        if value == "—":
            return self.cell_text(value, label_x, row_y, kind, cell, "end",
                                  attributes=f'data-point-id={quoteattr(self.project.points[index].id)}')
        transform = f'transform="translate({label_x} {row_y}) rotate(-90)"'
        return self.cell_text(value, 0, 0, kind, cell,
                              attributes=f'data-point-id={quoteattr(self.project.points[index].id)}', transform=transform)

    def point_name(self, index, occupied):
        """Разносит горизонтальные имена по строкам сбоку от вертикалей точек."""
        point = self.project.points[index]
        name = point.id + (" / " + self.bend_names[point.id] if point.id in self.bend_names else "")
        top = settings.PROFILE_DISTANCE_ROW_BOTTOM_MM
        bottom = settings.PROFILE_POINT_ROW_BOTTOM_MM
        cell = (settings.PROFILE_SIDEBAR_WIDTH_MM, top, self.point_x[-1] + settings.PROFILE_GRID_RIGHT_PADDING_MM, bottom)
        baseline = top + settings.PROFILE_CELL_PADDING_MM + self.drawing.style.base_size
        label_x = self.point_x[index] - settings.PROFILE_POINT_NAME_OFFSET_MM
        anchor = "end"
        if label_x - text_width(name, self.drawing.style.base_size) < settings.PROFILE_SIDEBAR_WIDTH_MM:
            label_x = self.point_x[index] + settings.PROFILE_POINT_NAME_OFFSET_MM
            anchor = "start"
        baseline = self.free_baseline(name, label_x, baseline, anchor, occupied,
                                      settings.PROFILE_POINT_NAME_ROWS)
        return self.cell_text(name, label_x, baseline, "point-name", cell, anchor,
                              attributes=f'data-point-id={quoteattr(point.id)}')

    def draw_values(self):
        """Возвращает отметки, горизонтальные имена, пикеты и вертикали таблицы."""
        elements, occupied = [], []
        for index, point in enumerate(self.project.points):
            values = [
                (format_number(self.drawing.bottom_levels[index]), settings.PROFILE_BOTTOM_LEVEL_Y_MM, "bottom-level",
                 0, settings.PROFILE_BOTTOM_LEVEL_ROW_BOTTOM_MM),
                (format_number(point.ground), settings.PROFILE_GROUND_LEVEL_Y_MM, "ground-level",
                 settings.PROFILE_BOTTOM_LEVEL_ROW_BOTTOM_MM, settings.PROFILE_GROUND_ROW_BOTTOM_MM),
                ("—", settings.PROFILE_NATURAL_GROUND_Y_MM, "natural-ground", settings.PROFILE_GROUND_ROW_BOTTOM_MM, settings.PROFILE_NATURAL_GROUND_ROW_BOTTOM_MM),
                (format_station(self.drawing.stations[index]), STATION_Y, "station",
                 settings.PROFILE_POINT_ROW_BOTTOM_MM, settings.PROFILE_GRID_HEIGHT_MM),
            ]
            for value, row_y, kind, row_top, row_bottom in values:
                elements.append(self.vertical_text(value, index, row_y, kind, row_top, row_bottom))
            elements.append(self.point_name(index, occupied))
            elements.append(f'<path d="M {self.point_x[index]},0 V {settings.PROFILE_NATURAL_GROUND_ROW_BOTTOM_MM} '
                            f'M {self.point_x[index]},{settings.PROFILE_SLOPE_ROW_BOTTOM_MM} V {settings.PROFILE_GRID_HEIGHT_MM}" '
                            f'fill="none" stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')
        return "\n".join(elements)

    def free_baseline(self, value, left, baseline, anchor, occupied, rows=settings.PROFILE_NUMBER_TEXT_ROWS, direction=1):
        """Выбирает свободную строку из соседних позиций и сохраняет габариты текста."""
        size = self.drawing.style.base_size
        step = size + settings.PROFILE_TEXT_ROW_GAP_MM
        for row in range(rows):
            candidate = baseline + direction * row * step
            bounds = text_bounds(value, left, candidate, size, anchor)
            if not any(labels_too_close(bounds, previous) for previous in occupied):
                occupied.append(bounds)
                return candidate
        occupied.append(text_bounds(value, left, baseline, size, anchor))
        return baseline

    def draw_slope(self, start_x, end_x, slope):
        """Возвращает SVG линии направления уклона или пустую строку без отметок."""
        if slope is None:
            return ""
        start_y = end_y = SLOPE_LINE_Y
        if slope > 0:
            start_y, end_y = settings.PROFILE_SLOPE_ROW_BOTTOM_MM, settings.PROFILE_BASE_ROW_BOTTOM_MM
        elif slope < 0:
            start_y, end_y = settings.PROFILE_BASE_ROW_BOTTOM_MM, settings.PROFILE_SLOPE_ROW_BOTTOM_MM
        return (f'<path data-kind="slope-line" d="M {start_x},{start_y} L {end_x},{end_y}" '
                f'fill="none" stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')

    def section_text(self, section, start_x, end_x, value, kind, occupied):
        """Располагает уклон и длину в противоположных углах, расстояние — внутри строки."""
        size, padding = self.drawing.style.base_size, settings.PROFILE_CELL_PADDING_MM
        upper_left = section["slope_per_mille"] is None or section["slope_per_mille"] >= 0
        if kind == "distance":
            left, anchor = (start_x + end_x) / 2, "middle"
            top, bottom = settings.PROFILE_SLOPE_ROW_BOTTOM_MM, settings.PROFILE_DISTANCE_ROW_BOTTOM_MM
            baseline, direction = top + padding + size, 1
        else:
            is_slope = kind == "slope"
            use_left = upper_left if is_slope else not upper_left
            left, anchor = (start_x + padding, "start") if use_left else (end_x - padding, "end")
            top, bottom = settings.PROFILE_BASE_ROW_BOTTOM_MM, settings.PROFILE_SLOPE_ROW_BOTTOM_MM
            baseline, direction = (top + padding + size, 1) if is_slope else (bottom - padding, -1)
        baseline = self.free_baseline(value, left, baseline, anchor, occupied, direction=direction)
        attributes = (f'data-start-id={quoteattr(section["start_id"])} '
                      f'data-end-id={quoteattr(section["end_id"])}')
        return self.cell_text(value, left, baseline, kind, (start_x, top, end_x, bottom), anchor, attributes)

    def draw_sections(self):
        """Возвращает диагонали и разнесённые подписи уклонов, длин и расстояний."""
        elements, occupied = [], []
        for index, section in enumerate(self.drawing.sections):
            start_x, end_x = self.point_x[index:index + 2]
            if index:
                elements.append(f'<line data-kind="slope-divider" x1="{start_x}" x2="{start_x}" '
                                f'y1="{settings.PROFILE_BASE_ROW_BOTTOM_MM}" y2="{settings.PROFILE_SLOPE_ROW_BOTTOM_MM}" '
                                f'stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')
            elements.append(self.draw_slope(start_x, end_x, section["slope_per_mille"]))
            for value, kind in [(format_slope(section["slope_per_mille"]), "slope"),
                                (format_number(section["length_m"]), "slope-length"),
                                (format_number(section["length_m"]), "distance")]:
                elements.append(self.section_text(section, start_x, end_x, value, kind, occupied))
        return "\n".join(elements)

    def pipe_labels(self):
        """Возвращает две строки трубы по справочнику материала и данным входа."""
        pipe, config = self.project.pipe, self.drawing.config["profile"]
        material = next((item for name, item in config["materials"].items()
                         if name != "default" and pipe.material.casefold().startswith(name.casefold())),
                        config["materials"]["default"])
        description = material["description"].format(material=pipe.material, sdr=format_pipe_value(pipe.sdr))
        standard = pipe.standard or material.get("standard", "")
        name = config["pipe_description"].format(
            material=description, diameter=format_pipe_value(pipe.outer_diameter_mm),
            wall=format_pipe_value(pipe.wall_mm), standard=" " + standard if standard else "")
        return {"pipe_name": escape(name),
                "insulation": escape(pipe.insulation or config["default_insulation"])}

    def depth_baseline(self, sheet_x, sheet_y, depth, occupied):
        """Разносит глубины близких точек по высоте и возвращает центр подписи."""
        size = self.drawing.style.base_size
        width = text_width(format_number(depth), size)
        minimum = settings.PROFILE_TEXT_TOP_MM + width / 2
        label_y = max(sheet_y - settings.PROFILE_DEPTH_LABEL_OFFSET_MM, minimum)
        bounds = (sheet_x - settings.PROFILE_LABEL_OFFSET_MM - size, label_y - width / 2,
                  sheet_x - settings.PROFILE_LABEL_OFFSET_MM, label_y + width / 2)
        while any(labels_too_close(bounds, other) for other in occupied):
            blockers = [other for other in occupied if labels_too_close(bounds, other)]
            next_y = min(other[1] for other in blockers) - settings.LABEL_MIN_GAP_MM - width / 2
            if next_y < minimum:
                break
            label_y = next_y
            bounds = (bounds[0], label_y - width / 2, bounds[2], label_y + width / 2)
        occupied.append(bounds)
        return label_y

    def projection_data(self):
        """Возвращает координаты проекций и габариты глубин без построения SVG."""
        drawing, occupied = self.drawing, []
        values = []
        for index, point in enumerate(self.project.points):
            level = point.ground if point.ground is not None else drawing.bottom_levels[index]
            if level is None:
                continue
            left = drawing.origin_x + drawing.stations[index] * drawing.mm_per_meter_x
            top = drawing.datum_y - (level - drawing.datum_level) * drawing.mm_per_meter_y
            depth = format_number(drawing.levels[index]["depth_to_bottom_m"])
            baseline = self.depth_baseline(left, top, drawing.levels[index]["depth_to_bottom_m"], occupied)
            values.append(Projection(point.id, left, top, depth, baseline, occupied[-1],
                                     occupied[-1][3] + settings.LABEL_MIN_GAP_MM <= top))
        return values

    def projection_labels(self):
        """Возвращает прямоугольники глубин непосредственно из расчёта размещения."""
        return [ProfileLabel(projection.depth, projection.bounds, None, "above")
                for projection in self.projection_data()]

    def draw_projections(self):
        """Возвращает проекции и глубины по общим данным размещения."""
        elements = [f'<g id="profile-projections" font-family="{settings.FONT_FAMILY}" '
                    f'font-size="{self.drawing.style.base_size}">']
        for projection in self.projection_data():
            elements.append(f'<path data-point-id={quoteattr(projection.name)} d="M {projection.left},{projection.top} V {self.drawing.datum_y}" '
                            f'stroke="black" stroke-width="{settings.PROFILE_GRID_LINE_WIDTH_MM}"/>')
            elements.append(f'<text data-kind="depth" data-placement="{"ok" if projection.fits else "warning"}" data-point-id={quoteattr(projection.name)} '
                            f'transform="translate({projection.left - settings.PROFILE_LABEL_OFFSET_MM} {projection.baseline}) rotate(-90)" '
                            f'text-anchor="middle">{projection.depth}</text>')
        return "\n".join(elements + ['</g>'])

    def scale_labels(self):
        """Возвращает надписи масштаба из единого набора строк шаблона."""
        labels = ["Масштаб:",
                  settings.PROFILE_SCALE_TEXT.format(direction="горизонтали", scale=self.drawing.horizontal_scale),
                  settings.PROFILE_SCALE_TEXT.format(direction="вертикали", scale=self.drawing.vertical_scale),
                  "УГ " + format_number(self.drawing.datum_level)]
        return list(zip(labels, settings.PROFILE_SCALE_BASELINES_MM))

    def draw_scale_labels(self):
        """Возвращает надписи масштаба через общий SVG-шаблон."""
        kinds = ("scale-title", "horizontal-scale", "vertical-scale", "datum")
        return "\n".join(render_template(TEMPLATES_DIR / "profile_scale_label.svg", {
            "kind": kind, "baseline": baseline, "value": escape(value),
        }) for (value, baseline), kind in zip(self.scale_labels(), kinds))

    def scale_obstacles(self):
        """Возвращает габариты масштаба и условного горизонта на листе."""
        left = self.drawing.origin_x - settings.PROFILE_POINT_ORIGIN_MM
        return [ProfileLabel(value, text_bounds(value, left, self.drawing.datum_y + baseline,
                                              self.drawing.style.base_size), None, "above")
                for value, baseline in self.scale_labels()]

    def render(self):
        """Возвращает SVG проекций и сетки с подставленными расчётными значениями."""
        drawing = self.drawing
        labels = self.pipe_labels()
        pipe_width = (text_width(unescape(labels["pipe_name"]), drawing.style.base_size)
                      + 2 * settings.PROFILE_CELL_PADDING_MM)
        width = max(self.point_x[-1] + settings.PROFILE_GRID_RIGHT_PADDING_MM, settings.PROFILE_SIDEBAR_WIDTH_MM + pipe_width)
        width = min(width, drawing.sheet.width - settings.SHEET_FRAME_RIGHT_MM - drawing.origin_x + settings.PROFILE_POINT_ORIGIN_MM)
        grid = render_template(TEMPLATE_PATH, {
            "left": drawing.origin_x - settings.PROFILE_POINT_ORIGIN_MM,
            "top": drawing.datum_y,
            "width": width,
            "middle": (settings.PROFILE_SIDEBAR_WIDTH_MM + width) / 2,
            "values": self.draw_values(),
            "sections": self.draw_sections(),
            **labels,
            "scale_labels": self.draw_scale_labels(),
            "font_size": drawing.style.base_size,
            "pipe_cell": f"{settings.PROFILE_SIDEBAR_WIDTH_MM} {settings.PROFILE_NATURAL_GROUND_ROW_BOTTOM_MM} {width} {settings.PROFILE_PIPE_ROW_BOTTOM_MM}",
            "font_family": settings.FONT_FAMILY,
            "grid_line_width": settings.PROFILE_GRID_LINE_WIDTH_MM,
            "sidebar_width": settings.PROFILE_SIDEBAR_WIDTH_MM,
            "grid_height": settings.PROFILE_GRID_HEIGHT_MM,
            "bottom_level_row_bottom": settings.PROFILE_BOTTOM_LEVEL_ROW_BOTTOM_MM,
            "ground_row_bottom": settings.PROFILE_GROUND_ROW_BOTTOM_MM,
            "natural_ground_row_bottom": settings.PROFILE_NATURAL_GROUND_ROW_BOTTOM_MM,
            "pipe_row_bottom": settings.PROFILE_PIPE_ROW_BOTTOM_MM,
            "base_row_bottom": settings.PROFILE_BASE_ROW_BOTTOM_MM,
            "slope_row_bottom": settings.PROFILE_SLOPE_ROW_BOTTOM_MM,
            "distance_row_bottom": settings.PROFILE_DISTANCE_ROW_BOTTOM_MM,
            "point_row_bottom": settings.PROFILE_POINT_ROW_BOTTOM_MM,
        })
        return self.draw_projections() + "\n" + grid
