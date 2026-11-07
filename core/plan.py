from math import atan2, degrees
from xml.sax.saxutils import escape, quoteattr

from core import drawing_settings as settings
from core.calculations import calculate_route_geometry
from core.formatting import format_number, format_pipe_value, format_station
from core.paths import TEMPLATES_DIR
from core.sheet import Sheet
from core.templates import render_template


LEGEND_PATH = TEMPLATES_DIR / "plan_legend.svg"


class PlanDrawing:
    """План трассы на листе A3 (SVG).

    Метры местности переводятся в мм листа по масштабу (по умолчанию 1:1000),
    трасса центрируется над штампом. Рисует линию трубы, имена и пикеты точек,
    координаты, длины участков, подпись трубы и легенду. render() возвращает строку SVG.
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

    def place_points(self):
        """Возвращает координаты точек в мм листа, центрируя трассу в свободном поле."""
        min_x = min(point.x for point in self.project.points)
        max_x = max(point.x for point in self.project.points)
        min_y = min(point.y for point in self.project.points)
        max_y = max(point.y for point in self.project.points)
        width = (max_x - min_x) * self.mm_per_meter
        height = (max_y - min_y) * self.mm_per_meter

        available_width = self.sheet.width - settings.PLAN_FIELD_HORIZONTAL_MARGINS_MM
        if width > available_width or height > settings.PLAN_FIELD_HEIGHT_MM:
            raise ValueError(
                f"Трасса не помещается на A3 при масштабе 1:{self.scale}. "
                "Требуется другой формат или масштаб."
            )

        left = settings.PLAN_FIELD_LEFT_MM + (available_width - width) / 2
        top = settings.PLAN_FIELD_TOP_MM + (settings.PLAN_FIELD_HEIGHT_MM - height) / 2
        coordinates = []
        for point in self.project.points:
            sheet_x = left + (point.x - min_x) * self.mm_per_meter
            sheet_y = top + (max_y - point.y) * self.mm_per_meter
            coordinates.append((sheet_x, sheet_y))
        return coordinates

    def draw_geometry(self):
        """Возвращает SVG штриховой линии трубы без условных знаков колодцев."""
        points = " ".join(f"{sheet_x},{sheet_y}" for sheet_x, sheet_y in self.coordinates)
        return "\n".join([
            f'<g id="route-geometry" data-scale="{self.scale}">',
            f'<polyline id="route-line" points="{points}" fill="none" stroke="black" '
            f'stroke-width="{settings.PLAN_ROUTE_LINE_WIDTH_MM}" '
            f'stroke-dasharray="{settings.PLAN_ROUTE_DASHARRAY_MM}" stroke-linejoin="miter"/>',
            '</g>',
        ])

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
        field_width = self.sheet.width - settings.PLAN_FIELD_HORIZONTAL_MARGINS_MM
        return settings.PLAN_FIELD_LEFT_MM + field_width / 2

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
        """Возвращает SVG имён точек и пикетов из расчётных накопленных расстояний."""
        elements = []
        for index, (point, (sheet_x, sheet_y)) in enumerate(zip(self.project.points, self.coordinates)):
            station = 0.0 if index == 0 else self.sections[index - 1]["cumsum_dist_m"]
            label_x, anchor = self.point_label_position(index)
            elements.append(
                f'<text data-kind="point-name" data-point-id={quoteattr(point.id)} '
                f'x="{label_x}" y="{sheet_y - settings.PLAN_POINT_NAME_OFFSET_MM}" '
                f'text-anchor="{anchor}">{self.point_title(point.id)}</text>'
            )
            elements.append(
                f'<text data-kind="station" data-point-id={quoteattr(point.id)} '
                f'x="{label_x}" y="{sheet_y - settings.PLAN_STATION_OFFSET_MM}" '
                f'text-anchor="{anchor}">{format_station(station)}</text>'
            )
        return "\n".join(elements)

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
        if abs(angle) > 90:
            angle += -180 if angle > 0 else 180
        center_x, center_y = (start_x + end_x) / 2, (start_y + end_y) / 2
        text = self.pipe_label_text()
        if abs(end_x - start_x) < 1e-7:
            return self.vertical_pipe_label(text, center_x, center_y)
        return (
            f'<text data-kind="pipe-label" text-anchor="middle" x="0" y="{settings.PLAN_PIPE_LABEL_OFFSET_MM}" '
            f'transform="translate({center_x:g} {center_y:g}) rotate({angle:g})">'
            f'{escape(text)}</text>'
        )

    def draw_coordinates(self):
        """Возвращает SVG исходных X и Y, отводя их от соседних участков и подписей."""
        elements = []
        for index, (point, (sheet_x, sheet_y)) in enumerate(zip(self.project.points, self.coordinates)):
            neighbors = self.coordinates[max(0, index - 1):index + 2]
            above_neighbor = any(neighbor_y < sheet_y for neighbor_x, neighbor_y in neighbors)
            if above_neighbor:
                label_y = sheet_y + settings.PLAN_COORDINATES_BELOW_OFFSET_MM
            else:
                label_y = sheet_y - settings.PLAN_COORDINATES_ABOVE_OFFSET_MM
            label = f"X={format_number(point.x)}, Y={format_number(point.y)}"
            elements.append(
                f'<text data-kind="coordinates" data-point-id={quoteattr(point.id)} '
                f'x="{sheet_x}" y="{label_y}" font-size="{settings.PLAN_COORDINATE_FONT_SIZE_MM}" '
                f'text-anchor="middle">{label}</text>'
            )
        return "\n".join(elements)

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

    def draw_lengths(self):
        """Возвращает SVG расчётных длин со сдвигом по нормали к каждому участку."""
        elements = []
        for index, section in enumerate(self.sections):
            start_x, start_y = self.coordinates[index]
            end_x, end_y = self.coordinates[index + 1]
            length_mm = section["length_m"] * self.mm_per_meter
            label_x = (start_x + end_x) / 2 - (end_y - start_y) / length_mm * settings.PLAN_LENGTH_OFFSET_MM
            label_y = ((start_y + end_y) / 2 + (end_x - start_x) / length_mm * settings.PLAN_LENGTH_OFFSET_MM
                       + settings.PLAN_TEXT_BASELINE_OFFSET_MM)
            elements.append(
                f'<text data-kind="length" data-start-id={quoteattr(section["start_id"])} '
                f'data-end-id={quoteattr(section["end_id"])} x="{label_x}" y="{label_y}" '
                f'text-anchor="middle">{format_number(section["length_m"])}</text>'
            )
        return "\n".join(elements)

    def render(self):
        """Возвращает готовый SVG-лист, сохраняя порядок геометрии, подписей и легенды."""
        # округляется только вывод подписей.
        labels = (f'<g id="route-labels" font-family="{settings.FONT_FAMILY}" '
                  f'font-size="{settings.PLAN_FONT_SIZE_MM}" fill="black">')
        elements = [
            self.draw_geometry(), labels,
            self.draw_point_labels(), self.draw_coordinates(), self.draw_lengths(), self.draw_pipe_label(), '</g>',
            self.draw_legend(),
        ]
        return self.sheet.render("\n".join(elements))
