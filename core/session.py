from dataclasses import asdict
from pathlib import Path

from core.calculations import (
    calculate_material_quantities,
    calculate_pipe_levels,
    calculate_route_geometry,
    calculate_route_length,
    load_project,
)
from core.documents import DocumentSet
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.models import (
    Change, ChangeSet, DocumentId, Level, PipeField, PointField,
    PIPE_WHERE, Problem, ProblemCode, Status, UNIT_M, UNIT_MM,
)
from core.profile_style import ProfileStyle
from core.release import create_package
from core.validate import validate_input


VALUES_UNCHANGED = "Значения не изменились."
POINT_NOT_FOUND = "Точка не найдена."
FIELDS_REQUIRED = "Укажите изменяемые x, y или z."
PIPE_FIELDS_REQUIRED = "Укажите изменяемые поля трубы: {fields}."
LABEL_ROUTE_LENGTH = "Общая длина трассы"
LABEL_PROFILE_FONT = "Базовый шрифт профиля"
LABEL_OBJECT_PIPE_MATERIAL = "Материал трубы в описании объекта"
TITLE_POINT_CHANGE = "Изменение точки {name}"
TITLE_FONT_CHANGE = "Изменение шрифта профиля"
TITLE_PIPE_CHANGE = "Изменение трубы"
INPUT_INVALID = "Исходные данные не прошли проверку."


class RouteSession:
    """Текущий проект и только успешно выпущенные изменения этой сессии."""

    def __init__(self, input_file, output_dir, config):
        self.project, self.problems = load_project(input_file)
        if self.project is None:
            raise ValueError("; ".join(problem.message for problem in self.problems))
        self.config = config
        self.documents = DocumentSet(self.project, self.config)
        self.output_dir = Path(output_dir)
        self.changes, self.tool_log = [], []
        self.font_size = DEFAULT_FONT_SIZE_MM

    @staticmethod
    def problem_response(status, problems, **extra):
        """Собирает ответ инструмента с прежним форматом списка проблем."""
        return {"status": status, **extra, "problems": [problem.to_dict() for problem in problems]}

    def error_response(self, code, message, where):
        """Возвращает ответ с одной ошибкой аргументов инструмента."""
        return self.problem_response(Status.ERROR, [Problem(Level.ERROR, code, message, where)])

    # Обёртки подставляют текущий проект в расчётные инструменты LLM.
    def calculate_route_length(self):
        if any(problem.blocks_length for problem in self.problems):
            return self.problem_response(Status.ERROR, self.problems)
        return self.problem_response(Status.OK, self.problems, **calculate_route_length(self.project))

    def calculate_pipe_levels(self):
        return self.problem_response(Status.OK, self.problems, **calculate_pipe_levels(self.project))

    def calculate_material_quantities(self):
        if any(problem.blocks_length for problem in self.problems):
            return self.problem_response(Status.ERROR, self.problems)
        blocking = [problem for problem in self.problems if problem.blocks_quantities]
        if blocking:
            return self.problem_response(Status.ERROR, blocking)
        return self.problem_response(Status.OK, self.problems, **calculate_material_quantities(self.project))

    def release(self):
        if self.has_errors(self.project, self.problems):
            return self.problem_response(Status.ERROR, self.problems, message=INPUT_INVALID)
        result = create_package(self.project, self.output_dir, self.config, self.changes, self.font_size)
        if "checks" in result:
            result["checks"] = [check.to_dict() for check in result["checks"]]
        return result

    @staticmethod
    def has_errors(project, problems):
        """Проверяет, отсутствует ли проект или есть ли ошибки проверки данных."""
        return project is None or any(problem.level == Level.ERROR for problem in problems)

    @staticmethod
    def parse_fields(values, field_enum):
        """Проверяет аргументы и возвращает поля модели либо None при неверных именах."""
        fields = {field.argument: field for field in field_enum}
        if not values or not set(values).issubset(fields):
            return None
        # Enum сопоставляет имена аргументов инструмента с полями модели.
        return {fields[name].attribute: value for name, value in values.items()}

    def publish_update(self, data, make_changes):
        """Проверяет новые данные и выпускает комплект; при ошибке проект не меняется."""
        project, problems = validate_input(data)
        if self.has_errors(project, problems):
            return self.problem_response(Status.ERROR, problems)
        return self.apply(project, make_changes(project), self.font_size)

    def all_sheets(self):
        """Возвращает названия всех листов из состава комплекта."""
        return [doc["short_title"] for doc in self.documents.items]

    @staticmethod
    def add_value(values, name, before, after, unit=UNIT_M):
        if before != after:
            values.append(Change(name, before, after, unit))

    def apply(self, project, change, font_size):
        result = create_package(project, self.output_dir, self.config, self.changes + [change], font_size)
        if result["status"] == Status.ERROR:
            return result
        self.project, self.font_size = project, font_size
        self.problems = []
        self.changes.append(change)
        response = {"status": result["status"], "changes": asdict(change), "pdf": result["pdf"]}
        if result["status"] == Status.WARNING:
            response["warnings"] = [check.message for check in result.get("checks", [])
                                    if check.status == Status.WARNING]
        return response

    def update_point(self, name, **values):
        """Готовит правку точки и передаёт её в общую транзакцию выпуска."""
        updates = self.parse_fields(values, PointField)
        if updates is None:
            return self.error_response(ProblemCode.FIELDS_REQUIRED, FIELDS_REQUIRED, name)
        point = next((point for point in self.project.points if point.id == name), None)
        if point is not None and all(getattr(point, field) == value for field, value in updates.items()):
            return {"status": Status.OK, "message": VALUES_UNCHANGED}
        data = self.project.with_point(name, **updates)
        if data is None:
            return self.error_response(ProblemCode.POINT_NOT_FOUND, POINT_NOT_FOUND, name)
        return self.publish_update(data, lambda project: self.point_changes(point, project))

    def point_changes(self, old_point, project) -> ChangeSet:
        new_point = next(point for point in project.points if point.id == old_point.id)
        values = []
        for field in PointField:
            self.add_value(values, f"{old_point.id}, {field.label}",
                           getattr(old_point, field.attribute), getattr(new_point, field.attribute), field.unit)
        before = calculate_route_geometry(self.project.points)["length_m"]
        after = calculate_route_geometry(project.points)["length_m"]
        self.add_value(values, LABEL_ROUTE_LENGTH, before, after)
        return ChangeSet(TITLE_POINT_CHANGE.format(name=old_point.id), values, self.all_sheets())

    def update_pipe(self, **values):
        """Готовит правку трубы и передаёт её в общую транзакцию выпуска."""
        updates = self.parse_fields(values, PipeField)
        if updates is None:
            message = PIPE_FIELDS_REQUIRED.format(fields=", ".join(field.argument for field in PipeField))
            return self.error_response(ProblemCode.FIELDS_REQUIRED, message, PIPE_WHERE)
        data = self.project.with_pipe(**updates)
        if data is None:
            return {"status": Status.OK, "message": VALUES_UNCHANGED}
        return self.publish_update(data, self.pipe_changes)

    def pipe_changes(self, project) -> ChangeSet:
        """Возвращает изменения полей трубы и перечень листов полного перевыпуска."""
        values = []
        for field in PipeField:
            self.add_value(values, field.label, getattr(self.project.pipe, field.attribute),
                           getattr(project.pipe, field.attribute), field.unit)
        self.add_value(values, LABEL_OBJECT_PIPE_MATERIAL,
                       self.project.object.pipe_material, project.object.pipe_material, "")
        return ChangeSet(TITLE_PIPE_CHANGE, values, self.all_sheets())

    def change_profile_font(self, direction):
        size = ProfileStyle.font_step(self.font_size, direction)
        if size == self.font_size:
            return {"status": Status.OK, "message": VALUES_UNCHANGED}
        values = []
        self.add_value(values, LABEL_PROFILE_FONT, self.font_size, size, UNIT_MM)
        change = ChangeSet(TITLE_FONT_CHANGE, values, [self.documents.get(DocumentId.PROFILE)["short_title"]])
        return self.apply(self.project, change, size)
