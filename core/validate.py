import math

from pydantic import ValidationError

from core.models import Level, Project


ANGLE_TOLERANCE_DEG = 0.5  # Допуск сравнения угла отвода, градусы.


def problem(level, where, message, blocks_length=False, blocks_quantities=False):
    return {
        "level": level,
        "where": where,
        "message": message,
        "blocks_length": blocks_length,
        "blocks_quantities": blocks_quantities,
    }


class InputValidator:
    """Проверка структуры проекта и согласованности его исходных данных."""

    def __init__(self, data):
        self.data = data
        self.project = None
        self.problems = []
        self.ids = []

    def validate(self):
        self.problems = []
        if not self.check_structure():
            return None, self.problems
        self.check_levels()
        self.check_ids()
        self.check_bends()
        self.check_materials()
        self.check_segments()
        self.check_bend_angles()
        return self.project, self.problems

    def check_structure(self):
        self.project = None
        self.ids = []
        try:
            self.project = Project.model_validate(self.data)
        except ValidationError as error:
            for item in error.errors():
                path = ".".join(str(part) for part in item["loc"])
                self.problems.append(problem(Level.ERROR, path, item["msg"]))
            return False
        self.ids = [point.id for point in self.project.points]
        return True

    def check_levels(self):
        for point in self.project.points:
            if point.axis is None:
                self.problems.append(problem(
                    Level.ERROR, point.id, "нет отметки оси трубы (axis)"
                ))
            if point.ground is None:
                self.problems.append(problem(
                    Level.ERROR, point.id, "нет отметки земли (ground)"
                ))

    def check_ids(self):
        for pid in set(self.ids):
            if self.ids.count(pid) > 1:
                self.problems.append(problem(
                    Level.ERROR, pid, "идентификатор точки повторяется",
                    blocks_length=True,
                ))

    def check_bends(self):
        for bend in self.project.bends:
            if bend.at not in self.ids:
                self.problems.append(problem(
                    Level.ERROR, bend.at, "отвод ссылается на несуществующую точку",
                    blocks_quantities=True,
                ))
        bend_points = [bend.at for bend in self.project.bends]
        for pid in set(bend_points):
            if bend_points.count(pid) > 1:
                self.problems.append(problem(
                    Level.ERROR, pid, "в одной точке повторно указан отвод",
                    blocks_quantities=True,
                ))

    def check_materials(self):
        if self.project.pipe.material != self.project.object.pipe_material:
            self.problems.append(problem(
                Level.ERROR, "pipe",
                f"материал трубы ({self.project.pipe.material}) не совпадает "
                f"с описанием объекта ({self.project.object.pipe_material})",
                blocks_quantities=True,
            ))

    def check_segments(self):
        for start, end in zip(self.project.points, self.project.points[1:]):
            if start.x == end.x and start.y == end.y:
                self.problems.append(problem(
                    Level.ERROR, f"{start.id}–{end.id}",
                    "соседние точки совпадают по X и Y: длина участка в плане равна нулю",
                    blocks_length=True,
                ))

    def turn_angle(self, index):
        before = self.project.points[index - 1]
        at = self.project.points[index]
        after = self.project.points[index + 1]
        ax, ay = at.x - before.x, at.y - before.y
        bx, by = after.x - at.x, after.y - at.y
        len_a = (ax ** 2 + ay ** 2) ** 0.5
        len_b = (bx ** 2 + by ** 2) ** 0.5
        if len_a == 0 or len_b == 0:
            return None  # Нулевой участок отмечает check_segments().
        cos_turn = (ax * bx + ay * by) / (len_a * len_b)
        cos_turn = max(-1.0, min(1.0, cos_turn))
        return math.degrees(math.acos(cos_turn))

    def check_bend_angles(self):
        for bend in self.project.bends:
            if bend.at not in self.ids:
                continue  # Несуществующую точку отмечает check_bends().
            index = self.ids.index(bend.at)
            if index == 0 or index == len(self.project.points) - 1:
                self.problems.append(problem(
                    Level.ERROR, bend.at,
                    "отвод указан в концевой точке трассы, где поворота нет",
                    blocks_quantities=True,
                ))
                continue
            turn_deg = self.turn_angle(index)
            if turn_deg is None:
                continue
            if abs(turn_deg - bend.angle_deg) > ANGLE_TOLERANCE_DEG:
                self.problems.append(problem(
                    Level.ERROR, bend.at,
                    f"угол отвода в данных {bend.angle_deg:g}, "
                    f"по координатам поворот {turn_deg:.1f}",
                    blocks_quantities=True,
                ))


def validate_input(data):
    return InputValidator(data).validate()
