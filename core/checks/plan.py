import math

from core.checks.base import BaseChecks, NS
from core.formatting import format_number, format_station
from core.models import DocumentId, Level


# Оценка средней ширины символа в долях размера шрифта; безразмерный приближённый коэффициент.
TEXT_WIDTH_FACTOR = 0.6


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
            if not math.isclose(end_coordinate[0]-start_coordinate[0], (end.x-start.x) * mm_per_meter, abs_tol=1e-7):
                self.add("plan_geometry", False, "Неверное направление или расстояние по X на плане.")
                return
            if not math.isclose(end_coordinate[1]-start_coordinate[1], (start.y-end.y) * mm_per_meter, abs_tol=1e-7):
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
        width = len("".join(element.itertext())) * TEXT_WIDTH_FACTOR * font_size
        left = float(element.get("x"))
        bottom = float(element.get("y"))
        anchor = element.get("text-anchor", "start")
        if anchor == "middle":
            left -= width / 2
        elif anchor == "end":
            left -= width
        return left, bottom - font_size, left + width, bottom

    def plan_labels(self, element, inherited_size, rotated=False):
        """Перебирает подписи с наследованием размера; трубу с rotate пропускает."""
        font_size = float(element.get("font-size", inherited_size))
        rotated = rotated or "rotate" in element.get("transform", "")
        if element.tag == f'{{{NS["s"]}}}text' and element.get("data-kind") in {
            "point-name", "station", "coordinates", "length", "pipe-label",
        }:
            if not (element.get("data-kind") == "pipe-label" and rotated):
                yield self.plan_label_name(element), self.plan_label_bounds(element, font_size)
        for child in element:
            yield from self.plan_labels(child, font_size, rotated)

    @staticmethod
    def rectangles_overlap(bounds, other):
        """Проверяет пересечение внутренних областей двух прямоугольников."""
        return (bounds[0] < other[2] and bounds[2] > other[0]
                and bounds[1] < other[3] and bounds[3] > other[1])

    @staticmethod
    def segment_crosses_rectangle(start, end, bounds):
        """Проверяет вход отрезка внутрь прямоугольника отсечением по двум осям."""
        if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            return False
        entry, exit = 0.0, 1.0
        for origin, finish, minimum, maximum in [
            (start[0], end[0], bounds[0], bounds[2]),
            (start[1], end[1], bounds[1], bounds[3]),
        ]:
            direction = finish - origin
            if abs(direction) < 1e-7:
                if not minimum < origin < maximum:
                    return False
            else:
                first = (minimum - origin) / direction
                second = (maximum - origin) / direction
                entry = max(entry, min(first, second))
                exit = min(exit, max(first, second))
                if entry >= exit:
                    return False
        return entry < exit

    def check_plan_label_overlap(self):
        """Добавляет предупреждение для каждой пары подписей или подписи и участка."""
        root = self.roots[DocumentId.PLAN]
        group = root.find("s:g[@id='route-labels']", NS)
        labels = list(self.plan_labels(group, 0))
        line = root.find(".//s:polyline[@id='route-line']", NS)
        points = [tuple(map(float, point.split(","))) for point in line.get("points").split()]
        tolerance = float(line.get("stroke-width")) / 2
        warnings = []
        for index, (name, bounds) in enumerate(labels):
            for other_name, other_bounds in labels[index + 1:]:
                if self.rectangles_overlap(bounds, other_bounds):
                    warnings.append(f"План: пересекаются подписи {name} и {other_name}.")
            # Границы текста приблизительны: касания в пределах полутолщины линии не учитываем.
            inner_bounds = (bounds[0] + tolerance, bounds[1] + tolerance,
                            bounds[2] - tolerance, bounds[3] - tolerance)
            for section, start, end in zip(self.geometry["sections"], points, points[1:]):
                if self.segment_crosses_rectangle(start, end, inner_bounds):
                    warnings.append(f'План: подпись {name} пересекает трассу на участке '
                                    f'{section["start_id"]}–{section["end_id"]}.')
        for message in warnings:
            self.add("plan_label_overlap", False, message, level=Level.WARNING)
        if not warnings:
            self.add("plan_label_overlap", True, "Приближённая проверка не выявила пересечений подписей плана.")

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        self.run_checks(self.check_plan_geometry, self.check_plan_labels, self.check_plan_coordinates, self.check_plan_label_overlap)
