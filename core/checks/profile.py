import math
import re

from core import drawing_settings as settings
from core.checks.base import BaseChecks, NS
from core.formatting import format_number, format_station
from core.models import DocumentId, Level
from core.profile_grid import POINT_ORIGIN


class ProfileChecks(BaseChecks):
    """Значения, масштабы и геометрия профиля."""

    def check_profile_values(self):
        """Сверяет значения сетки и подписи глубины с расчётом."""
        root = self.roots[DocumentId.PROFILE]
        expected = {"bottom-level": [format_number(point["bottom_m"]) for point in self.levels],
                    "ground-level": [format_number(point.ground) for point in self.project.points],
                    "station": [format_station(station) for station in self.stations],
                    "slope": [format_number(section["slope_per_mille"]) for section in self.geometry["sections"]],
                    "distance": [format_number(section["length_m"]) for section in self.geometry["sections"]]}
        for kind, values in expected.items():
            found = root.findall(f".//s:text[@data-kind='{kind}']", NS)
            if [element.text for element in found] != values:
                self.add("profile_values", False, "Значения профиля не совпадают с расчётом: " + kind)
                return
        depths = {point["point_id"]: format_number(point["depth_to_bottom_m"]) for point in self.levels}
        for element in root.findall(".//s:text[@data-kind='depth']", NS):
            if element.text != depths[element.get("data-point-id")]:
                self.add("profile_values", False, "Глубина на профиле не совпадает с расчётом.")
                return
        self.add("profile_values", True, "Отметки, глубины, уклоны, расстояния и пикеты совпадают с расчётом.")

    def profile_points(self, values, left, baseline, datum, horizontal_scale, vertical_scale):
        """Возвращает ожидаемые координаты и команды линии профиля."""
        coordinates, commands, connected = [], [], False
        for station, value in zip(self.stations, values):
            if value is None:
                connected = False
                continue
            coordinates.append((
                left + POINT_ORIGIN + station * 1000 / horizontal_scale,
                baseline - (value - datum) * 1000 / vertical_scale,
            ))
            commands.append("L" if connected else "M")
            connected = True
        return coordinates, commands

    def check_profile_line(self, line_id, values):
        """Сверяет точки и разрывы одной линии профиля с расчётом."""
        root = self.roots[DocumentId.PROFILE]
        group = root.find("s:g[@id='profile-geometry']", NS)
        grid = root.find("s:g[@id='profile-grid']", NS)
        left, baseline = map(float, re.findall(r'-?\d+(?:\.\d+)?', grid.get("transform")))
        expected, commands = self.profile_points(
            values, left, baseline, float(group.get("data-datum-m")),
            float(group.get("data-horizontal-scale")), float(group.get("data-vertical-scale")),
        )
        tokens = group.find(f"s:path[@id='{line_id}']", NS).get("d").split()
        actual = [tuple(map(float, item.split(","))) for item in tokens[1::2]]
        if tokens[::2] != commands or len(actual) != len(expected):
            self.add(line_id, False, "Неверное число точек или разрывы линии профиля.")
            return
        if not all(math.dist(actual_point, expected_point) < 1e-7 for actual_point, expected_point in zip(actual, expected)):
            self.add(line_id, False, "Положение линии профиля не совпадает с отметками и пикетами.")
            return
        self.add(line_id, True, "Линия профиля соответствует отметкам; пропуски не соединены.")

    def check_profile_geometry(self):
        """Сверяет подписи масштабов, интервалы точек и линии профиля."""
        root = self.roots[DocumentId.PROFILE]
        group = root.find("s:g[@id='profile-geometry']", NS)
        horizontal_scale = float(group.get("data-horizontal-scale"))
        vertical_scale = float(group.get("data-vertical-scale"))
        for kind, scale, direction in [
            ("horizontal-scale", group.get("data-horizontal-scale"), "горизонтали"),
            ("vertical-scale", group.get("data-vertical-scale"), "вертикали"),
        ]:
            label = root.find(f".//s:text[@data-kind='{kind}']", NS)
            if label is None or label.text != f"М 1:{scale} по {direction}":
                self.add("profile_scale", False, "Подпись масштаба профиля не совпадает с геометрией.")
                return
        self.add("profile_scale", True, f"Масштабы профиля 1:{horizontal_scale:g} и 1:{vertical_scale:g}.")
        self.check_profile_spacing(horizontal_scale)
        self.check_profile_line("ground-line", [point.ground for point in self.project.points])
        self.check_profile_line("pipe-bottom-line", [point["bottom_m"] for point in self.levels])
        top = group.find("s:path[@id='pipe-top-line']", NS)
        diameter = self.project.pipe.outer_diameter_mm
        if diameter / vertical_scale >= settings.PROFILE_TWO_LINE_THRESHOLD_MM:
            self.check_profile_line("pipe-top-line", [None if point["bottom_m"] is None else
                                    point["bottom_m"] + diameter / 1000 for point in self.levels])
        elif top is not None:
            self.add("pipe-top-line", False, f"При диаметре менее {settings.PROFILE_TWO_LINE_THRESHOLD_MM:g} мм в масштабе должен быть один контур.")

    def check_profile_spacing(self, horizontal_scale):
        """Предупреждает о тесных колонках профиля, сохраняя возможность выпуска."""
        if any((end - start) * 1000 / horizontal_scale < settings.PROFILE_MIN_POINT_SPACING_MM
               for start, end in zip(self.stations, self.stations[1:])):
            self.add("profile_point_spacing", False,
                     "Профиль: точки ближе 8 мм на листе; подписи требуют визуальной проверки.", level=Level.WARNING)
        else:
            self.add("profile_point_spacing", True, "Интервалы точек профиля не меньше 8 мм на листе.")

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        return self.run_checks(self.check_profile_values, self.check_profile_geometry)
