import math

from core import drawing_settings as settings
from core.checks.base import BaseChecks, NS
from core.formatting import format_number, format_station
from core.models import DocumentId, Level
from core.label_geometry import labels_too_close, rectangles_overlap, segment_crosses_rectangle, text_bounds
from core.pipe_drawing import pipe_line_count
from core.pipe_geometry import PipeContours


class PlanChecks(BaseChecks):
    """Геометрия, подписи и приближённая проверка пересечений плана."""

    def check_plan_geometry(self):
        """Сверяет участки плана с координатами проекта и масштабом."""
        group = self.roots[DocumentId.PLAN].find("s:g[@id='route-geometry']", NS)
        scale = float(group.get("data-scale"))
        mm_per_meter = 1000 / scale
        line = group.find("s:polyline[@id='route-line']", NS)
        coordinates = [tuple(map(float, coordinate_text.split(","))) for coordinate_text in line.get("points").split()]
        if len(coordinates) != len(self.project.points):
            self.add("plan_geometry", False, "Количество точек плана не совпадает с исходными данными.")
            return
        for index in range(len(self.project.points) - 1):
            start_coordinate, end_coordinate = coordinates[index:index+2]
            start, end = self.project.points[index:index+2]
            if not math.isclose(end_coordinate[0]-start_coordinate[0], (end.x-start.x) * mm_per_meter,
                                abs_tol=settings.GEOMETRY_TOLERANCE_MM):
                self.add("plan_geometry", False, "Неверное направление или расстояние по X на плане.")
                return
            if not math.isclose(end_coordinate[1]-start_coordinate[1], (start.y-end.y) * mm_per_meter,
                                abs_tol=settings.GEOMETRY_TOLERANCE_MM):
                self.add("plan_geometry", False, "Неверное направление или расстояние по Y на плане.")
                return
        self.add("plan_geometry", True, f"Геометрия плана соответствует координатам и масштабу 1:{scale:g}.")

    def check_plan_labels(self):
        """Сверяет подписи пикетов и длин плана с расчётом."""
        root = self.roots[DocumentId.PLAN]
        stations = root.findall(".//s:text[@data-kind='station']", NS)
        if [element.text for element in stations] != [format_station(station) for station in self.stations]:
            self.add("plan_labels", False, "Пикетаж плана не совпадает с расчётом.")
            return
        lengths = root.findall(".//s:text[@data-kind='length']", NS)
        if [element.text for element in lengths] != [format_number(section["length_m"]) for section in self.geometry["sections"]]:
            self.add("plan_labels", False, "Подписи длин участков плана не совпадают с расчётом.")
            return
        self.add("plan_labels", True, "Пикеты, длины, легенда и линия трубы присутствуют.")

    def check_plan_coordinates(self):
        """Сверяет подписи координат с точками проекта."""
        labels = self.roots[DocumentId.PLAN].findall(".//s:text[@data-kind='coordinates']", NS)
        expected = [(point.id, f"X={format_number(point.x)}, Y={format_number(point.y)}") for point in self.project.points]
        if [(element.get("data-point-id"), element.text) for element in labels] != expected:
            self.add("coordinates", False, "Координаты у точек плана не совпадают с исходными данными.")
            return
        self.add("coordinates", True, "У каждой точки плана подписаны её исходные X и Y.")

    @staticmethod
    def plan_label_name(element):
        """Возвращает текст подписи с привязкой к участку или точке."""
        name = '"' + "".join(element.itertext()) + '"'
        if element.get("data-kind") == "length":
            return f'{name} (длина {element.get("data-start-id")}–{element.get("data-end-id")})'
        if element.get("data-kind") != "point-name" and element.get("data-point-id"):
            return f'{name} (точка {element.get("data-point-id")})'
        return name

    @staticmethod
    def plan_label_bounds(element, font_size):
        """Возвращает приближённые границы текста: слева, сверху, справа, снизу, в мм."""
        return text_bounds("".join(element.itertext()), float(element.get("x")), float(element.get("y")),
                           font_size, element.get("text-anchor", "start"))

    def plan_labels(self, element, inherited_size, rotated=False):
        """Перебирает подписи с наследованием размера; трубу с rotate пропускает."""
        font_size = float(element.get("font-size", inherited_size))
        rotated = rotated or "rotate" in element.get("transform", "")
        if element.get("data-kind") == "pipe-label" and element.get("data-bounds"):
            yield '"' + " / ".join(element.itertext()).strip() + '" (полка трубы)', tuple(map(float, element.get("data-bounds").split()))
            return
        if element.tag == f'{{{NS["s"]}}}text' and element.get("data-kind") in {
            "point-name", "station", "coordinates", "length", "pipe-label",
        }:
            if not (element.get("data-kind") == "pipe-label" and rotated):
                yield self.plan_label_name(element), self.plan_label_bounds(element, font_size)
        for child in element:
            yield from self.plan_labels(child, font_size, rotated)

    rectangles_overlap = staticmethod(rectangles_overlap)
    segment_crosses_rectangle = staticmethod(segment_crosses_rectangle)

    def check_plan_label_overlap(self):
        """Добавляет предупреждение для каждой пары подписей или подписи и участка."""
        root = self.roots[DocumentId.PLAN]
        group = root.find("s:g[@id='route-labels']", NS)
        labels = list(self.plan_labels(group, 0))
        line = root.find(".//s:polyline[@id='route-line']", NS)
        points = [tuple(map(float, point.split(","))) for point in line.get("points").split()]
        scale = float(root.find("s:g[@id='route-geometry']", NS).get("data-scale", settings.PLAN_SCALE))
        diameter = self.project.pipe.outer_diameter_mm / scale
        tolerance = float(line.get("stroke-width")) / 2
        warnings = []
        for index, (name, bounds) in enumerate(labels):
            for other_name, other_bounds in labels[index + 1:]:
                if labels_too_close(bounds, other_bounds):
                    warnings.append(f"План: пересекаются или слишком близки подписи {name} и {other_name}.")
            # Границы текста приблизительны: касания в пределах полутолщины линии не учитываем.
            inner_bounds = (bounds[0] + tolerance, bounds[1] + tolerance,
                            bounds[2] - tolerance, bounds[3] - tolerance)
            if pipe_line_count(self.project.pipe.outer_diameter_mm, scale) == 2:
                inner_bounds = (inner_bounds[0] - diameter / 2, inner_bounds[1] - diameter / 2,
                                inner_bounds[2] + diameter / 2, inner_bounds[3] + diameter / 2)
            for section, start, end in zip(self.geometry["sections"], points, points[1:]):
                if self.segment_crosses_rectangle(start, end, inner_bounds):
                    warnings.append(f'План: подпись {name} пересекает трассу на участке '
                                    f'{section["start_id"]}–{section["end_id"]}.')
        for message in warnings:
            self.add("plan_label_overlap", False, message, level=Level.WARNING)
        if not warnings:
            self.add("plan_label_overlap", True, "Приближённая проверка не выявила пересечений подписей плана.")

    def check_plan_pipe(self):
        """Проверяет число контуров и подпись трубы по данным проекта."""
        root = self.roots[DocumentId.PLAN]
        group = root.find("s:g[@id='route-geometry']", NS)
        scale = float(group.get("data-scale"))
        count = pipe_line_count(self.project.pipe.outer_diameter_mm, scale)
        contours = group.findall("s:g[@id='pipe-contours']/s:path", NS)
        self.add("plan_pipe", len(contours) == (2 if count == 2 else 0),
                 f"План: число линий трубы — {count}; диаметр на листе {format_number(self.project.pipe.outer_diameter_mm / scale)} мм.",
                 reference=settings.PIPE_STYLE_REFERENCE)
        self.check_pipe_label(DocumentId.PLAN)

    def check_plan_bends(self):
        """Проверяет место для касательных дуг в вершинах с отводами."""
        group = self.roots[DocumentId.PLAN].find("s:g[@id='route-geometry']", NS)
        scale = float(group.get("data-scale"))
        count = pipe_line_count(self.project.pipe.outer_diameter_mm, scale)
        if count == 1:
            self.add("plan_bends", True, "Отводы показаны условными углами.", reference=settings.BEND_REFERENCE)
            return
        points = [tuple(map(float, pair.split(","))) for pair in group.find("s:polyline[@id='route-line']", NS).get("points").split()]
        bend_ids = {bend.at for bend in self.project.bends}
        indices = {index for index, point in enumerate(self.project.points) if point.id in bend_ids}
        geometry = PipeContours(points, indices, self.project.pipe.outer_diameter_mm / scale)
        crowded = [corner for corner in geometry.corners if corner.tangent > corner.available]
        for corner in crowded:
            self.add("plan_bends", False, settings.BEND_SPACE_WARNING.format(
                point=self.project.points[corner.index].id, tangent=format_number(corner.tangent),
                available=format_number(corner.available)), level=Level.WARNING, reference=settings.BEND_REFERENCE)
        if not crowded:
            self.add("plan_bends", True, "Для дуг отводов достаточно места на соседних участках.", reference=settings.BEND_REFERENCE)

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        return self.run_checks(self.check_plan_geometry, self.check_plan_labels, self.check_plan_coordinates,
                               self.check_plan_pipe, self.check_plan_bends, self.check_plan_label_overlap)
