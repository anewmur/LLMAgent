from math import hypot
from xml.sax.saxutils import escape, quoteattr, unescape

from config import drawing_settings as settings
from core.calculations import calculate_route_geometry
from core.formatting import format_number, format_station, format_point_title
from config.paths import TEMPLATES_DIR
from core.sheet import Sheet
from core.drawing_scale import choose_plan_scale
from core.pipe_drawing import pipe_line_count, pipe_leader
from core.pipe_geometry import PipeContours
from core.tables import text_width
from core.label_geometry import plan_label_width, text_bounds, labels_too_close, segment_crosses_rectangle
from core.formatting import render_template


LEGEND_PATH = TEMPLATES_DIR / "plan_legend.svg"
POINT_MARKER_PATH = TEMPLATES_DIR / "plan_point_marker.svg"
POINT_LABEL_PATH = TEMPLATES_DIR / "plan_point_label.svg"
POINT_LEADER_PATH = TEMPLATES_DIR / "plan_point_leader.svg"


class PlanDrawing:
    """План трассы на листе A3 (SVG).

    Метры местности переводятся в мм листа по автоматически выбранному масштабу,
    трасса центрируется над штампом. Рисует трубу с кружками вершин, блоки имён,
    пикетов и координат, длины, подпись трубы и легенду. render() возвращает SVG.
    """

    def __init__(self, project, document, scale=None):
        """Готовит лист, координаты и участки трассы в заданном масштабе."""
        scale = choose_plan_scale(project, scale)
        self.project = project
        self.scale = scale
        self.mm_per_meter = 1000 / self.scale
        self.sheet = Sheet(document["designation"], project.object.name,
                           f'{document["title"]} (1:{self.scale})')
        self.coordinates = self.place_points()
        self.sections = calculate_route_geometry(project.points)["sections"]
        self.bends = {bend.at: bend for bend in project.bends}
        self.bend_names = project.bend_names()
        self.line_count = pipe_line_count(project.pipe.outer_diameter_mm, scale)
        bend_indices = {index for index, point in enumerate(project.points) if point.id in self.bends}
        self.pipe_geometry = PipeContours(self.coordinates, bend_indices, project.pipe.outer_diameter_mm / scale)
        self.marker_coordinates = self.pipe_geometry.marker_points() if self.line_count == 2 else self.coordinates

    @property
    def field_width(self):
        """Возвращает ширину свободного поля в мм листа."""
        return self.sheet.width - settings.PLAN_FIELD_HORIZONTAL_MARGINS_MM

    @property
    def field_right(self):
        """Возвращает правую границу свободного поля в мм листа."""
        return settings.PLAN_FIELD_LEFT_MM + self.field_width

    def place_points(self):
        """Возвращает координаты точек в мм листа, центрируя трассу в свободном поле."""
        min_x = min(point.x for point in self.project.points)
        max_x = max(point.x for point in self.project.points)
        min_y = min(point.y for point in self.project.points)
        max_y = max(point.y for point in self.project.points)
        width = (max_x - min_x) * self.mm_per_meter
        height = (max_y - min_y) * self.mm_per_meter

        left = settings.PLAN_FIELD_LEFT_MM + (self.field_width - width) / 2
        top = settings.PLAN_FIELD_TOP_MM + (settings.PLAN_FIELD_HEIGHT_MM - height) / 2
        coordinates = []
        for point in self.project.points:
            sheet_x = left + (point.x - min_x) * self.mm_per_meter
            sheet_y = top + (max_y - point.y) * self.mm_per_meter
            coordinates.append((sheet_x, sheet_y))
        return coordinates

    def draw_geometry(self):
        """Возвращает SVG штриховой трубы и белых кружков в её вершинах."""
        points = " ".join(f"{sheet_x},{sheet_y}" for sheet_x, sheet_y in self.coordinates)
        return "\n".join([
            f'<g id="route-geometry" data-scale="{self.scale}" data-line-count="{self.line_count}">',
            f'<polyline id="route-line" points="{points}" display="{"none" if self.line_count == 2 else "inline"}" visibility="{"hidden" if self.line_count == 2 else "visible"}" fill="none" stroke="black" '
            f'stroke-width="{settings.PLAN_ROUTE_LINE_WIDTH_MM}" '
            f'stroke-dasharray="{settings.PLAN_ROUTE_DASHARRAY_MM}" stroke-linejoin="miter"/>',
            self.draw_pipe_contours() if self.line_count == 2 else "",
            self.draw_point_markers(),
            '</g>',
        ])

    def draw_point_markers(self):
        """Возвращает кружки из шаблона; белая заливка перекрывает штрих трубы."""
        return "\n".join(render_template(POINT_MARKER_PATH, {
            "point_id": quoteattr(point.id), "point_x": sheet_x, "point_y": sheet_y,
            "radius": settings.POINT_MARKER_DIAMETER_MM / 2,
            "line_width": settings.POINT_MARKER_LINE_WIDTH_MM,
        }) for point, (sheet_x, sheet_y) in zip(self.project.points, self.marker_coordinates))

    def point_title(self, point_id):
        """Возвращает экранированное имя точки с номером УП и непрямым углом."""
        return escape(format_point_title(point_id, self.bends.get(point_id), self.bend_names.get(point_id)))

    def field_center_x(self):
        """Возвращает абсциссу центра свободного поля в мм листа."""
        return settings.PLAN_FIELD_LEFT_MM + self.field_width / 2

    def point_label_position(self, index):
        """Возвращает абсциссу подписи в мм листа и её SVG-выравнивание."""
        sheet_x, sheet_y = self.marker_coordinates[index]
        neighbors = self.coordinates[max(0, index - 1):index + 2]
        upper = [(neighbor_x, neighbor_y) for neighbor_x, neighbor_y in neighbors if neighbor_y < sheet_y]
        # Подпись выше точки уводим от участка, направленного вверх.
        place_left = upper[0][0] >= sheet_x if upper else sheet_x > self.field_center_x()
        if place_left:
            return sheet_x - settings.PLAN_POINT_LABEL_SIDE_OFFSET_MM, "end"
        return sheet_x + settings.PLAN_POINT_LABEL_SIDE_OFFSET_MM, "start"

    def draw_point_labels(self):
        """Возвращает блоки имени, пикета и координат на одной стороне каждой точки."""
        obstacles = []
        for index, section in enumerate(self.sections):
            text = format_number(section["length_m"])
            center_x, center_y = self.length_label_center(index, text)
            obstacles.append(text_bounds(text, center_x, center_y + settings.PLAN_FONT_SIZE_MM / 2,
                                         settings.PLAN_FONT_SIZE_MM, "middle"))
        return "\n".join(self.draw_point_label(index, obstacles) for index in range(len(self.project.points)))

    def draw_point_label(self, index, obstacles):
        """Возвращает один блок подписей из шаблона с необязательной выноской."""
        point = self.project.points[index]
        station = 0.0 if index == 0 else self.sections[index - 1]["cumsum_dist_m"]
        values = {
            "point_id": quoteattr(point.id), "title": self.point_title(point.id),
            "station": format_station(station),
            "coordinates": f"X={format_number(point.x)}, Y={format_number(point.y)}",
            "coordinate_size": settings.PLAN_COORDINATE_FONT_SIZE_MM,
        }
        values.update(self.point_label_layout(index, values, obstacles))
        return render_template(POINT_LABEL_PATH, values)

    @staticmethod
    def label_width(values):
        """Возвращает приближённую ширину блока подписей в мм листа."""
        return plan_label_width(unescape(values["title"]), values["station"], values["coordinates"])

    def point_label_layout(self, index, values, obstacles):
        """Выбирает свободное положение блока внутри поля и добавляет его к препятствиям."""
        width = self.label_width(values)
        initial_x, anchor = self.point_label_position(index)
        left = initial_x - width if anchor == "end" else initial_x
        left = max(settings.PLAN_FIELD_LEFT_MM, min(left, self.field_right - width))
        label_x = left + width if anchor == "end" else left
        point_y = self.marker_coordinates[index][1]
        baselines = list(self.label_baselines(point_y))
        label_y = next((baseline for baseline in baselines
                        if self.label_fits(self.label_bounds(left, baseline, width), obstacles)), baselines[0])
        obstacles.append(self.label_bounds(left, label_y, width))
        leader = ""
        if (label_x, label_y) != (initial_x, point_y):
            leader = self.point_label_leader(index, left, label_y, width)
        return {"label_x": label_x, "anchor": anchor, "leader": leader,
                "name_y": label_y - settings.PLAN_POINT_NAME_OFFSET_MM,
                "station_y": label_y - settings.PLAN_STATION_OFFSET_MM,
                "coordinates_y": label_y - settings.PLAN_COORDINATES_ABOVE_OFFSET_MM}

    @staticmethod
    def label_bounds(left, baseline, width):
        """Возвращает общий прямоугольник трёх строк подписей точки в мм листа."""
        return (left, baseline - settings.PLAN_POINT_NAME_OFFSET_MM - settings.PLAN_FONT_SIZE_MM,
                left + width, baseline - settings.PLAN_COORDINATES_ABOVE_OFFSET_MM)

    def label_baselines(self, point_y):
        """Перебирает исходное положение, затем сдвиги вверх и вниз с шагом высоты блока."""
        top = settings.PLAN_FIELD_TOP_MM
        baseline = max(point_y, top + settings.PLAN_POINT_NAME_OFFSET_MM + settings.PLAN_FONT_SIZE_MM)
        yield baseline
        block_height = (settings.PLAN_POINT_NAME_OFFSET_MM + settings.PLAN_FONT_SIZE_MM
                        - settings.PLAN_COORDINATES_ABOVE_OFFSET_MM)
        step = block_height + settings.LABEL_MIN_GAP_MM
        for index in range(1, int(settings.PLAN_FIELD_HEIGHT_MM / step) + 1):
            yield baseline - index * step
            yield baseline + index * step

    def label_fits(self, bounds, obstacles):
        """Проверяет поле, расстояния до подписей и пересечение блока с трубой."""
        field_bottom = settings.PLAN_FIELD_TOP_MM + settings.PLAN_FIELD_HEIGHT_MM
        if bounds[1] < settings.PLAN_FIELD_TOP_MM or bounds[3] > field_bottom:
            return False
        if any(labels_too_close(bounds, other) for other in obstacles):
            return False
        clearance = self.pipe_geometry.diameter / 2 if self.line_count == 2 else 0
        pipe_bounds = (bounds[0] - clearance, bounds[1] - clearance,
                       bounds[2] + clearance, bounds[3] + clearance)
        return not any(segment_crosses_rectangle(start, end, pipe_bounds)
                       for start, end in zip(self.coordinates, self.coordinates[1:]))

    def point_label_leader(self, index, left, label_y, width):
        """Возвращает короткую линию от края кружка к ближайшему краю сдвинутого блока."""
        point_x, point_y = self.marker_coordinates[index]
        bounds = self.label_bounds(left, label_y, width)
        end_x = max(left, min(point_x, left + width))
        end_y = max(bounds[1], min(point_y, bounds[3]))
        distance = hypot(end_x - point_x, end_y - point_y)
        radius = settings.POINT_MARKER_DIAMETER_MM / 2
        if distance <= radius:
            return ""
        return render_template(POINT_LEADER_PATH, {
            "point_id": quoteattr(self.project.points[index].id),
            "start_x": point_x + (end_x - point_x) * radius / distance,
            "start_y": point_y + (end_y - point_y) * radius / distance,
            "end_x": end_x, "end_y": end_y, "line_width": settings.PLAN_PIPE_LEADER_WIDTH_MM,
        })

    def draw_pipe_contours(self):
        """Возвращает два сплошных контура с дугами и необязательной осью."""
        axis = ""
        if settings.DRAW_PIPE_AXIS:
            axis = render_template(TEMPLATES_DIR / "pipe_axis.svg", {
                "path": self.pipe_geometry.path_data(0), "line_width": settings.PIPE_AXIS_LINE_WIDTH_MM,
                "dasharray": settings.PIPE_AXIS_DASHARRAY_MM,
            })
        return render_template(TEMPLATES_DIR / "pipe_contours.svg", {
            "left": self.pipe_geometry.path_data(self.pipe_geometry.diameter / 2),
            "right": self.pipe_geometry.path_data(-self.pipe_geometry.diameter / 2),
            "line_width": settings.PLAN_ROUTE_LINE_WIDTH_MM, "axis": axis,
        })

    def draw_pipe_label(self):
        """Возвращает общую полку с обозначением и размером у самого длинного участка."""
        index = max(range(len(self.sections)), key=lambda section_index: self.sections[section_index]["length_m"])
        start_x, start_y = self.coordinates[index]
        end_x, end_y = self.coordinates[index + 1]
        length = hypot(end_x - start_x, end_y - start_y)
        label = format_number(self.sections[index]["length_m"])
        shift = min(text_width(label, settings.PLAN_FONT_SIZE_MM) / 2
                    + settings.PLAN_LEADER_LENGTH_CLEARANCE_MM, length / 4)
        target = ((start_x + end_x) / 2 + (end_x - start_x) / length * shift,
                  (start_y + end_y) / 2 + (end_y - start_y) / length * shift)
        direction = 1 if target[0] < self.field_center_x() else -1
        vertical = abs(end_x - start_x) < abs(end_y - start_y)
        shelf_y = target[1] - settings.PIPE_SHELF_VERTICAL_OFFSET_MM
        if not vertical:
            length_center = self.length_label_center(index, format_number(self.sections[index]["length_m"]))
            shelf_y = max(target[1] + settings.PIPE_SHELF_VERTICAL_OFFSET_MM,
                          length_center[1] + settings.PLAN_FONT_SIZE_MM / 2 + settings.PLAN_LENGTH_OFFSET_MM
                          + settings.PIPE_LABEL_FONT_SIZE_MM + settings.PIPE_SHELF_TEXT_GAP_MM)
        shelf = (target[0] + direction * settings.PIPE_SHELF_SIDE_OFFSET_MM, shelf_y)
        return pipe_leader(self.project.pipe, target, shelf, direction)

    def draw_legend(self):
        """Возвращает SVG легенды, подставляя общий шрифт и настройки линии трассы."""
        return render_template(LEGEND_PATH, {
            "network_code": settings.NETWORK_CODE,
            "single_display": "none" if self.line_count == 2 else "inline",
            "double_symbols": render_template(TEMPLATES_DIR / "plan_legend_double.svg", {
                "line_width": settings.PLAN_ROUTE_LINE_WIDTH_MM,
                "axis_display": "inline" if settings.DRAW_PIPE_AXIS else "none",
                "axis_width": settings.PIPE_AXIS_LINE_WIDTH_MM,
                "axis_dash": settings.PIPE_AXIS_DASHARRAY_MM,
            }) if self.line_count == 2 else "",
            "font_family": settings.FONT_FAMILY,
            "font_size": settings.PLAN_FONT_SIZE_MM,
            "line_width": settings.PLAN_ROUTE_LINE_WIDTH_MM,
            "line_dasharray": settings.PLAN_ROUTE_DASHARRAY_MM,
        })

    def segment_normal(self, index):
        """Возвращает единичную нормаль к участку в мм листа; на эту сторону ставятся подписи."""
        start_x, start_y = self.coordinates[index]
        end_x, end_y = self.coordinates[index + 1]
        length_mm = hypot(end_x - start_x, end_y - start_y)
        return -(end_y - start_y) / length_mm, (end_x - start_x) / length_mm

    def length_label_half_extent(self, index, text):
        """Возвращает полуразмер рамки подписи длины по нормали к участку, мм листа."""
        normal_x, normal_y = self.segment_normal(index)
        return (text_width(text, settings.PLAN_FONT_SIZE_MM) / 2 * abs(normal_x)
                + settings.PLAN_FONT_SIZE_MM / 2 * abs(normal_y))

    def length_label_center(self, index, text):
        """Возвращает центр подписи длины с заданным зазором от участка до ближайшей точки её рамки."""
        (start_x, start_y), (end_x, end_y) = self.coordinates[index], self.coordinates[index + 1]
        normal_x, normal_y = self.segment_normal(index)
        contour_offset = self.pipe_geometry.diameter / 2 if self.line_count == 2 else 0
        offset = settings.PLAN_LENGTH_OFFSET_MM + contour_offset + self.length_label_half_extent(index, text)
        return (start_x + end_x) / 2 + normal_x * offset, (start_y + end_y) / 2 + normal_y * offset

    def draw_lengths(self):
        """Возвращает SVG расчётных длин, отодвинутых по нормали к каждому участку."""
        elements = []
        for index, section in enumerate(self.sections):
            text = format_number(section["length_m"])
            center_x, center_y = self.length_label_center(index, text)
            # Рамка текста — от базовой линии вверх на размер шрифта, поэтому базовая линия ниже центра на половину.
            elements.append(
                f'<text data-kind="length" data-start-id={quoteattr(section["start_id"])} '
                f'data-end-id={quoteattr(section["end_id"])} x="{center_x}" '
                f'y="{center_y + settings.PLAN_FONT_SIZE_MM / 2}" text-anchor="middle">{text}</text>'
            )
        return "\n".join(elements)

    def render(self):
        """Возвращает готовый SVG-лист, сохраняя порядок геометрии, подписей и легенды."""
        # округляется только вывод подписей.
        labels = (f'<g id="route-labels" font-family="{settings.FONT_FAMILY}" '
                  f'font-size="{settings.PLAN_FONT_SIZE_MM}" fill="black">')
        elements = [
            self.draw_geometry(), labels,
            self.draw_point_labels(), self.draw_lengths(), self.draw_pipe_label(), '</g>',
            self.draw_legend(),
        ]
        return self.sheet.render("\n".join(elements))
