import math

from pydantic import ValidationError

from core.formatting import format_number, format_pipe_value
from core.models import PIPE_WHERE, Level, Problem, ProblemCode, Project
from core.settings import BEND_ANGLE_MESSAGE, MISSING_BEND_MESSAGE, PIPE_SDR_TOLERANCE, MISSING_AXIS_MESSAGE


ANGLE_TOLERANCE_DEG = 0.5  # Допуск сравнения угла отвода, градусы.


class InputValidator:
    """Проверка структуры проекта и согласованности его исходных данных."""

    def __init__(self, data):
        self.data = data
        self.project = None
        self.problems: list[Problem] = []
        self.ids = []

    def validate(self) -> tuple[Project | None, list[Problem]]:
        self.problems = []
        if not self.check_structure():
            return None, self.problems
        self.check_levels()
        self.check_ids()
        self.check_bends()
        self.check_materials()
        self.check_pipe_sdr()
        self.check_segments()
        self.check_bend_angles()
        self.check_unbent_turns()
        return self.project, self.problems

    def check_structure(self):
        self.project = None
        self.ids = []
        try:
            self.project = Project.model_validate(self.data)
        except ValidationError as error:
            for item in error.errors():
                path = ".".join(str(part) for part in item["loc"])
                self.problems.append(Problem(Level.ERROR, ProblemCode.STRUCTURE, item["msg"], path))
            return False
        self.ids = [point.id for point in self.project.points]
        return True

    def check_levels(self):
        for point in self.project.points:
            if point.axis is None:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.MISSING_AXIS, MISSING_AXIS_MESSAGE, point.id
                ))
            if point.ground is None:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.MISSING_GROUND, "нет отметки земли (ground)", point.id
                ))

    def check_ids(self):
        for point_id in set(self.ids):
            if self.ids.count(point_id) > 1:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.DUPLICATE_POINT, "идентификатор точки повторяется", point_id,
                ))

    def check_bends(self):
        for bend in self.project.bends:
            if bend.at not in self.ids:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.MISSING_BEND_POINT, "отвод ссылается на несуществующую точку", bend.at,
                ))
        bend_points = [bend.at for bend in self.project.bends]
        for point_id in set(bend_points):
            if bend_points.count(point_id) > 1:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.DUPLICATE_BEND, "в одной точке повторно указан отвод", point_id,
                ))

    def check_materials(self):
        if self.project.pipe.material != self.project.object.pipe_material:
            self.problems.append(Problem(
                Level.ERROR, ProblemCode.MATERIAL_CONFLICT,
                f"материал трубы ({self.project.pipe.material}) не совпадает "
                f"с описанием объекта ({self.project.object.pipe_material})",
                where=PIPE_WHERE,
            ))

    def check_pipe_sdr(self):
        """Проверяет соответствие наружного диаметра, стенки и SDR."""
        pipe = self.project.pipe
        calculated_sdr = pipe.outer_diameter_mm / pipe.wall_mm
        if abs(calculated_sdr - pipe.sdr) > PIPE_SDR_TOLERANCE:
            self.problems.append(Problem(
                Level.ERROR, ProblemCode.PIPE_SDR_MISMATCH,
                f"наружный диаметр {format_pipe_value(pipe.outer_diameter_mm)} мм и стенка {format_pipe_value(pipe.wall_mm)} мм "
                f"дают SDR {format_number(calculated_sdr)}, указан SDR {format_pipe_value(pipe.sdr)}; "
                f"допустимое расхождение — {format_pipe_value(PIPE_SDR_TOLERANCE)}",
                where=PIPE_WHERE,
            ))

    def check_segments(self):
        for start, end in zip(self.project.points, self.project.points[1:]):
            if start.x == end.x and start.y == end.y:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.ZERO_LENGTH,
                    "соседние точки совпадают по X и Y: длина участка в плане равна нулю",
                    where=f"{start.id}–{end.id}",
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
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.END_BEND,
                    "отвод указан в концевой точке трассы, где поворота нет", where=bend.at,
                ))
                continue
            turn_deg = self.turn_angle(index)
            if turn_deg is None:
                continue
            if abs(turn_deg - bend.angle_deg) > ANGLE_TOLERANCE_DEG:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.BEND_ANGLE,
                    BEND_ANGLE_MESSAGE.format(angle=format_pipe_value(bend.angle_deg),
                                              turn=format_pipe_value(turn_deg)),
                    where=bend.at,
                ))

    def check_unbent_turns(self):
        """Отмечает внутренние повороты трассы, для которых не задан отвод."""
        bend_points = {bend.at for bend in self.project.bends}
        for index in range(1, len(self.project.points) - 1):
            point = self.project.points[index]
            if point.id in bend_points:
                continue
            angle = self.turn_angle(index)
            if angle is not None and angle > ANGLE_TOLERANCE_DEG:
                self.problems.append(Problem(
                    Level.ERROR, ProblemCode.MISSING_BEND,
                    MISSING_BEND_MESSAGE.format(angle=format_number(angle)), where=point.id,
                ))


def validate_input(data) -> tuple[Project | None, list[Problem]]:
    return InputValidator(data).validate()
