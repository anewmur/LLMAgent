from math import atan2, degrees, hypot
from xml.sax.saxutils import escape, quoteattr, unescape

from core import drawing_settings as settings
from core.calculations import calculate_route_geometry
from core.formatting import format_number, format_pipe_value, format_station
from core.paths import TEMPLATES_DIR
from core.sheet import Sheet
from core.tables import text_width
from core.formatting import render_template


LEGEND_PATH = TEMPLATES_DIR / "plan_legend.svg"
POINT_MARKER_PATH = TEMPLATES_DIR / "plan_point_marker.svg"
POINT_LABEL_PATH = TEMPLATES_DIR / "plan_point_label.svg"
POINT_LEADER_PATH = TEMPLATES_DIR / "plan_point_leader.svg"


class PlanDrawing:
    """План трассы на листе A3 (SVG).

    Метры местности переводятся в мм листа по масштабу (по умолчанию 1:1000),
    трасса центрируется над штампом. Рисует трубу с кружками вершин, блоки имён,
    пикетов и координат, длины, подпись трубы и легенду. render() возвращает SVG.
    """

    def __init__(self, project, document, scale=settings.PLAN_SCALE):
        """Готовит лист, координаты и участки трассы в заданном масштабе."""
        if scale <= 0:
            raise ValueError("Масштаб должен быть положительным.")
        self.project = project
        self.scale = scale
        self.mm_per_meter = 1000 / self.scale
        self.sheet = Sheet(document["designation"], project.object.name,
                           f'{document["title"]} (1:{self.scale})')
        self.coordinates = self.place_points()
        self.sections = calculate_route_geometry(project.points)["sections"]
        self.bends = {bend.at: bend for bend in project.bends}
        self.bend_names = project.bend_names()

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

        if width > self.field_width or height > settings.PLAN_FIELD_HEIGHT_MM:
            raise ValueError(
                f"Трасса не помещается на A3 при масштабе 1:{self.scale}. "
                "Требуется другой формат или масштаб."
            )

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
            f'<g id="route-geometry" data-scale="{self.scale}">',
            f'<polyline id="route-line" points="{points}" fill="none" stroke="black" '
            f'stroke-width="{settings.PLAN_ROUTE_LINE_WIDTH_MM}" '
            f'stroke-dasharray="{settings.PLAN_ROUTE_DASHARRAY_MM}" stroke-linejoin="miter"/>',
            self.draw_point_markers(),
            '</g>',
        ])

    def draw_point_markers(self):
        """Возвращает кружки из шаблона; белая заливка перекрывает штрих трубы."""
        return "\n".join(render_template(POINT_MARKER_PATH, {
            "point_id": quoteattr(point.id), "point_x": sheet_x, "point_y": sheet_y,
            "radius": settings.POINT_MARKER_DIAMETER_MM / 2,
            "line_width": settings.POINT_MARKER_LINE_WIDTH_MM,
        }) for point, (sheet_x, sheet_y) in zip(self.project.points, self.coordinates))

    def point_title(self, point_id):
        """Возвращает экранированное имя точки с номером УП и непрямым углом."""
        title = point_id
        if point_id in self.bends:
            title += f" / {self.bend_names[point_id]}"
            # ГОСТ 21.704, п. 5.1.2: числовое значение 90° не указывают.
            angle_minutes = round(self.bends[point_id].angle_deg * 60)
            if angle_minutes != 90 * 60:
                degrees_part, minutes_part = divmod(angle_minutes, 60)
                title += f" ({degrees_part}°{minutes_part:02d}′)"
        return escape(title)

    def field_center_x(self):
        """Возвращает абсциссу центра свободного поля в мм листа."""
        return settings.PLAN_FIELD_LEFT_MM + self.field_width / 2

    def point_label_position(self, index):
        """Возвращает абсциссу подписи в мм листа и её SVG-выравнивание."""
        sheet_x, sheet_y = self.coordinates[index]
        neighbors = self.coordinates[max(0, index - 1):index + 2]
        upper = [(neighbor_x, neighbor_y) for neighbor_x, neighbor_y in neighbors if neighbor_y < sheet_y]
        # Подпись выше точки уводим от участка, направленного вверх.
        place_left = upper[0][0] >= sheet_x if upper else sheet_x > self.field_center_x()
        if place_left:
            return sheet_x - settings.PLAN_POINT_LABEL_SIDE_OFFSET_MM, "end"
        return sheet_x + settings.PLAN_POINT_LABEL_SIDE_OFFSET_MM, "start"

    def draw_point_labels(self):
        """Возвращает блоки имени, пикета и координат на одной стороне каждой точки."""
        return "\n".join(self.draw_point_label(index) for index in range(len(self.project.points)))

    def draw_point_label(self, index):
        """Возвращает один блок подписей из шаблона с необязательной выноской."""
        point = self.project.points[index]
        station = 0.0 if index == 0 else self.sections[index - 1]["cumsum_dist_m"]
        values = {
            "point_id": quoteattr(point.id), "title": self.point_title(point.id),
            "station": format_station(station),
            "coordinates": f"X={format_number(point.x)}, Y={format_number(point.y)}",
            "coordinate_size": settings.PLAN_COORDINATE_FONT_SIZE_MM,
        }
        values.update(self.point_label_layout(index, values))
        return render_template(POINT_LABEL_PATH, values)

    @staticmethod
    def label_width(values):
        """Возвращает приближённую ширину блока подписей в мм листа."""
        return max(text_width(unescape(values["title"]), settings.PLAN_FONT_SIZE_MM),
                   text_width(values["station"], settings.PLAN_FONT_SIZE_MM),
                   text_width(values["coordinates"], settings.PLAN_COORDINATE_FONT_SIZE_MM))

    def point_label_layout(self, index, values):
        """Возвращает общее положение строк, сдвигая блок внутрь поля чертежа."""
        width = self.label_width(values)
        initial_x, anchor = self.point_label_position(index)
        left = initial_x - width if anchor == "end" else initial_x
        left = max(settings.PLAN_FIELD_LEFT_MM, min(left, self.field_right - width))
        label_x = left + width if anchor == "end" else left
        point_y = self.coordinates[index][1]
        label_y = max(point_y, settings.PLAN_FIELD_TOP_MM + settings.PLAN_POINT_NAME_OFFSET_MM
                      + settings.PLAN_FONT_SIZE_MM)
        leader = ""
        if (label_x, label_y) != (initial_x, point_y):
            leader = self.point_label_leader(index, left, label_y, width)
        return {"label_x": label_x, "anchor": anchor, "leader": leader,
                "name_y": label_y - settings.PLAN_POINT_NAME_OFFSET_MM,
                "station_y": label_y - settings.PLAN_STATION_OFFSET_MM,
                "coordinates_y": label_y - settings.PLAN_COORDINATES_ABOVE_OFFSET_MM}

    def point_label_leader(self, index, left, label_y, width):
        """Возвращает короткую линию от края кружка к ближайшему краю сдвинутого блока."""
        point_x, point_y = self.coordinates[index]
        top = label_y - settings.PLAN_POINT_NAME_OFFSET_MM - settings.PLAN_FONT_SIZE_MM
        bottom = label_y - settings.PLAN_COORDINATES_ABOVE_OFFSET_MM
        end_x = max(left, min(point_x, left + width))
        end_y = max(top, min(point_y, bottom))
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

    def pipe_label_text(self):
        """Возвращает обозначение трубы с материалом, SDR, диаметром и стенкой."""
        pipe = self.project.pipe
        diameter = format_pipe_value(pipe.outer_diameter_mm)
        wall = format_pipe_value(pipe.wall_mm)
        sdr = format_pipe_value(pipe.sdr)
        return f"{settings.NETWORK_CODE} — {pipe.material} SDR {sdr} ⌀{diameter}×{wall}"

    def draw_pipe_label(self):
        """Возвращает SVG одной подписи трубы у самого длинного участка."""
        index = max(range(len(self.sections)), key=lambda section_index: self.sections[section_index]["length_m"])
        start_x, start_y = self.coordinates[index]
        end_x, end_y = self.coordinates[index + 1]
        angle = degrees(atan2(end_y - start_y, end_x - start_x))
        offset = settings.PLAN_PIPE_LABEL_OFFSET_MM
        if abs(angle) > 90:
            angle += -180 if angle > 0 else 180
        else:
            # Подпись трубы на стороне подписи длины: ставим её за рамкой длины с тем же зазором.
            length_text = format_number(self.sections[index]["length_m"])
            length_far = settings.PLAN_LENGTH_OFFSET_MM + 2 * self.length_label_half_extent(index, length_text)
            offset = max(offset, length_far + settings.PLAN_LENGTH_OFFSET_MM + settings.PLAN_FONT_SIZE_MM)
        center_x, center_y = (start_x + end_x) / 2, (start_y + end_y) / 2
        text = self.pipe_label_text()
        if abs(end_x - start_x) < settings.GEOMETRY_TOLERANCE_MM:
            return self.vertical_pipe_label(text, center_x, center_y)
        return (
            f'<text data-kind="pipe-label" text-anchor="middle" x="0" y="{offset:g}" '
            f'transform="translate({center_x:g} {center_y:g}) rotate({angle:g})">'
            f'{escape(text)}</text>'
        )

    def vertical_pipe_label(self, text, sheet_x, sheet_y):
        """Возвращает SVG выноски трубы выше подписи длины вертикального участка."""
        direction = 1 if sheet_x < self.field_center_x() else -1
        anchor = "start" if direction == 1 else "end"
        leader_y = sheet_y - settings.PLAN_FONT_SIZE_MM
        return (
            f'<g><path d="M {sheet_x},{leader_y} h {direction * settings.PLAN_PIPE_LEADER_LENGTH_MM}" '
            f'stroke="black" stroke-width="{settings.PLAN_PIPE_LEADER_WIDTH_MM}"/>'
            f'<text data-kind="pipe-label" font-size="{settings.PLAN_FONT_SIZE_MM}" '
            f'x="{sheet_x + direction * settings.PLAN_PIPE_LEADER_TEXT_OFFSET_MM}" '
            f'y="{leader_y - settings.PLAN_TEXT_BASELINE_OFFSET_MM}" text-anchor="{anchor}">{escape(text)}</text></g>'
        )

    def draw_legend(self):
        """Возвращает SVG легенды, подставляя общий шрифт и настройки линии трассы."""
        return render_template(LEGEND_PATH, {
            "network_code": settings.NETWORK_CODE,
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
        offset = settings.PLAN_LENGTH_OFFSET_MM + self.length_label_half_extent(index, text)
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
