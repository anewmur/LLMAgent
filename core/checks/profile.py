import math
import re

from config import drawing_settings as settings
from core.checks.base import BaseChecks, NS
from core.formatting import format_number, format_station, format_slope
from core.models import DocumentId, Level
from core.pipe_drawing import pipe_line_count
from core.profile_labels import ProfileLabels
from core.label_geometry import labels_too_close, rectangles_overlap


class ProfileChecks(BaseChecks):
    """Значения, масштабы и геометрия профиля."""

    def check_profile_values(self):
        """Сверяет значения сетки и подписи глубины с расчётом."""
        root = self.roots[DocumentId.PROFILE]
        expected = {"bottom-level": [format_number(point["bottom_m"]) for point in self.levels],
                    "ground-level": [format_number(point.ground) for point in self.project.points],
                    "station": [format_station(station) for station in self.stations],
                    "slope": [format_slope(section["slope_per_mille"]) for section in self.geometry["sections"]],
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
                left + settings.PROFILE_POINT_ORIGIN_MM + station * 1000 / horizontal_scale,
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
        if not all(math.dist(actual_point, expected_point) < settings.GEOMETRY_TOLERANCE_MM
                   for actual_point, expected_point in zip(actual, expected)):
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
            if label is None or label.text != settings.PROFILE_SCALE_TEXT.format(direction=direction, scale=scale):
                self.add("profile_scale", False, "Подпись масштаба профиля не совпадает с геометрией.")
                return
        self.add("profile_scale", True, f"Масштабы профиля 1:{horizontal_scale:g} и 1:{vertical_scale:g}.")
        self.check_profile_spacing(horizontal_scale)
        self.check_profile_line("ground-line", [point.ground for point in self.project.points])
        self.check_profile_line("pipe-bottom-line", [point["bottom_m"] for point in self.levels])
        top = group.find("s:path[@id='pipe-top-line']", NS)
        diameter = self.project.pipe.outer_diameter_mm
        if pipe_line_count(diameter, vertical_scale) == 2:
            self.check_profile_line("pipe-top-line", [None if point["bottom_m"] is None else
                                    point["bottom_m"] + diameter / 1000 for point in self.levels])
        elif top is not None:
            self.add("pipe-top-line", False, f"При диаметре менее {settings.PIPE_TWO_LINE_THRESHOLD_MM:g} мм в масштабе должен быть один контур.")

    def check_profile_spacing(self, horizontal_scale):
        """Предупреждает о тесных колонках профиля, сохраняя возможность выпуска."""
        if any((end - start) * 1000 / horizontal_scale < settings.PROFILE_MIN_POINT_SPACING_MM
               for start, end in zip(self.stations, self.stations[1:])):
            self.add("profile_point_spacing", False,
                     f"Профиль: точки ближе {settings.PROFILE_MIN_POINT_SPACING_MM:g} мм на листе; подписи требуют визуальной проверки.", level=Level.WARNING)
        else:
            self.add("profile_point_spacing", True, f"Интервалы точек профиля не меньше {settings.PROFILE_MIN_POINT_SPACING_MM:g} мм на листе.")

    def check_profile_pipe(self):
        """Сверяет число линий профиля и полку двухлинейного изображения."""
        root = self.roots[DocumentId.PROFILE]
        group = root.find("s:g[@id='profile-geometry']", NS)
        scale = float(group.get("data-vertical-scale"))
        expected = pipe_line_count(self.project.pipe.outer_diameter_mm, scale)
        actual = 1 + int(group.find("s:path[@id='pipe-top-line']", NS) is not None)
        self.add("profile_pipe", actual == expected, f"Профиль: число линий трубы — {expected}.",
                 reference=settings.PIPE_LINE_REFERENCE)
        if expected == 2:
            self.check_pipe_label(DocumentId.PROFILE)

    def check_profile_text_overlap(self):
        """Предупреждает о пересечениях текстов таблицы, глубин, полки и заголовка."""
        labels = self.labels.items
        conflicts = []
        for index, label in enumerate(labels):
            for other in labels[index + 1:]:
                if labels_too_close(label.bounds, other.bounds):
                    area = "таблица" if label.region == other.region == "table" else "над профилем"
                    conflicts.append(f'Профиль ({area}): пересекаются или слишком близки подписи «{label.text}» и «{other.text}».')
        for message in conflicts:
            self.add("profile_text_overlap", False, message, level=Level.WARNING)
        if not conflicts:
            self.add("profile_text_overlap", True, "Пересечений прямоугольников подписей профиля не обнаружено.")

    def check_profile_text_bounds(self):
        """Предупреждает о выходе подписи из своей клетки или за поле над профилем."""
        labels = self.labels.items
        violations = []
        for label in labels:
            if label.region == "table" and label.cell:
                left, top, right, bottom = label.cell
            elif label.region == "above" and label.text != settings.TRAINING_LABEL:
                left, top = settings.SHEET_FRAME_LEFT_MM, settings.PROFILE_TEXT_TOP_MM
                right, bottom = settings.SHEET_WIDTH_MM - settings.SHEET_FRAME_RIGHT_MM, settings.SHEET_HEIGHT_MM
            else:
                continue
            tolerance = settings.GEOMETRY_TOLERANCE_MM
            if (label.bounds[0] < left - tolerance or label.bounds[1] < top - tolerance
                    or label.bounds[2] > right + tolerance or label.bounds[3] > bottom + tolerance):
                violations.append(f'Профиль: подпись «{label.text}» выходит за границы '
                                  + ("своей клетки." if label.cell else "поля над профилем."))
        for message in violations:
            self.add("profile_text_bounds", False, message, level=Level.WARNING)
        if not violations:
            self.add("profile_text_bounds", True, "Подписи находятся внутри своих клеток и поля профиля.")

    def check_profile_shelf_space(self):
        """Предупреждает, если ни на одном участке не нашлось места для полки."""
        group = self.roots[DocumentId.PROFILE].find(".//s:g[@id='profile-pipe-label']", NS)
        if group is not None:
            fits = group.get("data-placement") == "ok"
            self.add("profile_shelf_space", fits, "Полка трубы размещена над землёй без пересечения препятствий."
                     if fits else "Профиль: свободное место для полки над землёй не найдено; нужна ручная компоновка.",
                     level=Level.WARNING)

    def check_profile_field(self):
        """Проверяет весь график земли и трубы относительно поля под учебной надписью."""
        root = self.roots[DocumentId.PROFILE]
        violations = []
        for name in ("ground-line", "pipe-bottom-line", "pipe-top-line"):
            line = root.find(f".//s:path[@id='{name}']", NS)
            if line is not None:
                for pair in line.get("d").split()[1::2]:
                    left, top = map(float, pair.split(","))
                    if top - float(line.get("stroke-width", 0)) / 2 < settings.PROFILE_TEXT_TOP_MM:
                        violations.append(name)
                        break
        self.add("profile_field", not violations, "График выходит выше границы поля под учебной надписью."
                 if violations else "Земля и труба находятся ниже границы поля.", level=Level.WARNING)

    def check_depth_space(self):
        """Предупреждает, если подпись глубины не помещается между землёй и границей поля."""
        depths = self.roots[DocumentId.PROFILE].findall(".//s:text[@data-kind='depth']", NS)
        for depth in depths:
            if depth.get("data-placement") == "warning":
                self.add("profile_depth_space", False,
                         f'Нет свободного места для глубины у точки {depth.get("data-point-id")}; подпись оставлена внутри поля.',
                         level=Level.WARNING)

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        self.labels = ProfileLabels(self.roots[DocumentId.PROFILE])
        return self.run_checks(self.check_profile_values, self.check_profile_geometry, self.check_profile_pipe,
                               self.check_profile_text_overlap, self.check_profile_text_bounds, self.check_profile_shelf_space, self.check_profile_field, self.check_depth_space)
