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
from core.check_report import CheckReport
from core.formatting import render_template
from core.paths import PROJECT_ROOT, TEMPLATES_DIR
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.models import (
    Change, ChangeSet, DocumentId, Level, PipeField, PointField,
    PIPE_WHERE, Problem, ProblemCode, Status, UNIT_DEGREE, UNIT_M, UNIT_MM,
)
from core.profile_style import ProfileStyle
from core.release import create_package, clear_output
from core.settings import (
    INPUT_DIR, LOAD_ROUTE_DATA_ERROR, LOAD_ROUTE_ERROR, LOAD_ROUTE_PATH_ERROR, LOG_WARNING_LABEL, TOOL_LOG_FILENAME,
    UPDATE_REJECTED_MESSAGE, BEND_NOT_FOUND, BEND_FIELDS_REQUIRED,
    TITLE_ADD_POINT, TITLE_REMOVE_POINT, TITLE_ADD_BEND, TITLE_REMOVE_BEND,
    LABEL_POINT_VALUE, LABEL_BEND_ANGLE,
    USAGE_LOG_HEADING,
)
from core.validate import validate_input


VALUES_UNCHANGED = "Значения не изменились."
POINT_NOT_FOUND = "Точка не найдена."
FIELDS_REQUIRED = (
    "Укажите изменяемые координаты x, y, отметку земли ground, "
    "отметку оси трубы axis или отводы bends."
)
PIPE_FIELDS_REQUIRED = "Укажите изменяемые поля трубы: {fields}."
LABEL_ROUTE_LENGTH = "Общая длина трассы"
LABEL_PROFILE_FONT = "Базовый шрифт профиля"
LABEL_OBJECT_PIPE_MATERIAL = "Материал трубы в описании объекта"
TITLE_POINT_CHANGE = "Изменение точки {name}"
TITLE_FONT_CHANGE = "Изменение шрифта профиля"
TITLE_PIPE_CHANGE = "Изменение трубы"
INPUT_INVALID = "Исходные данные не прошли проверку."


class RouteSession:
    """Текущий редактируемый проект и принятые изменения этой сессии."""

    def __init__(self, input_file, output_dir, config):
        self.project, self.problems = load_project(input_file)
        if self.project is None:
            raise ValueError("; ".join(problem.message for problem in self.problems))
        self.config = config
        self.documents = DocumentSet(self.project, self.config)
        self.output_dir = Path(output_dir)
        self.changes, self.tool_log = [], []
        self.usage_log = []
        self.font_size = DEFAULT_FONT_SIZE_MM

    def save_tool_log(self):
        """Сохраняет журнал текущей сессии в Markdown, заменяя прежний файл."""
        rows = []
        for entry in self.tool_log:
            if "warning" in entry:
                cells = (entry["turn"], LOG_WARNING_LABEL, entry["warning"], Status.WARNING)
            else:
                cells = (entry["turn"], entry["tool"], entry["arguments"], entry["result"].get("status", Status.OK))
            cells = [str(value).replace("|", "\\|").replace("\r", "").replace("\n", "<br>") for value in cells]
            rows.append("| " + " | ".join(cells) + " |")
        summaries = [entry["summary"] for entry in self.usage_log]
        usage = "\n\n".join([USAGE_LOG_HEADING, *summaries, self.usage_log[-1]["session_summary"]]) if self.usage_log else ""
        text = render_template(TEMPLATES_DIR / TOOL_LOG_FILENAME, {"rows": "\n".join(rows), "usage": usage})
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / TOOL_LOG_FILENAME).write_text(text, encoding="utf-8")

    @staticmethod
    def problem_response(status, problems, **extra):
        """Собирает ответ инструмента с прежним форматом списка проблем."""
        return {"status": status, **extra, "problems": [{"code": problem.code, **problem.to_dict()} for problem in problems]}

    def error_response(self, code, message, where):
        """Возвращает ответ с одной ошибкой аргументов инструмента."""
        return self.problem_response(
            Status.ERROR, [Problem(Level.ERROR, code, message, where)], message=UPDATE_REJECTED_MESSAGE,
        )

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

    def refuse_release(self, problems):
        """Очищает старый комплект и сохраняет отчёт об отказе по исходным данным."""
        clear_output(self.output_dir)
        result = self.problem_response(Status.ERROR, problems, released=False, message=INPUT_INVALID)
        result["report"] = CheckReport.write_rejection(self.output_dir, result["problems"])
        return result

    def release(self):
        """Возвращает результат выпуска, включая проверки и допущения отчёта."""
        if self.has_errors(self.project, self.problems):
            return self.refuse_release(self.problems)
        result = create_package(self.project, self.output_dir, self.config, self.changes, self.font_size)
        if "checks" in result:
            result["checks"] = [check.to_dict() for check in result["checks"]]
        return result

    def load_route(self, path):
        """Переключается на разобранную трассу и пробует выпустить комплект."""
        try:
            input_path = Path(path)
            if input_path.is_absolute():
                return self.problem_response(Status.ERROR, [Problem(Level.ERROR, ProblemCode.STRUCTURE, LOAD_ROUTE_PATH_ERROR)], message=LOAD_ROUTE_PATH_ERROR)
            input_path = (PROJECT_ROOT / input_path).resolve()
            if not input_path.is_relative_to(INPUT_DIR.resolve()):
                return self.problem_response(Status.ERROR, [Problem(Level.ERROR, ProblemCode.STRUCTURE, LOAD_ROUTE_PATH_ERROR)], message=LOAD_ROUTE_PATH_ERROR)
            loaded = RouteSession(input_path, self.output_dir, self.config)
        except (OSError, ValueError, TypeError) as error:
            return self.problem_response(Status.ERROR, [Problem(Level.ERROR, ProblemCode.STRUCTURE, LOAD_ROUTE_ERROR.format(error=error))], message=LOAD_ROUTE_ERROR.format(error=error))
        self.project, self.problems, self.documents = loaded.project, loaded.problems, loaded.documents
        self.changes, self.font_size = loaded.changes, loaded.font_size
        result = self.release()
        if result["status"] == Status.ERROR:
            return {**result, "message": LOAD_ROUTE_DATA_ERROR}
        return {**result, "object_name": self.project.object.name,
                "point_count": len(self.project.points),
                "length_m": calculate_route_geometry(self.project.points)["length_m"]}

    @staticmethod
    def has_errors(project, problems):
        """Проверяет, отсутствует ли проект или есть ли ошибки проверки данных."""
        return project is None or any(problem.level == Level.ERROR for problem in problems)

    @staticmethod
    def parse_fields(values, field_enum, allow_empty=False):
        """Проверяет аргументы и возвращает поля модели либо None при неверных именах."""
        fields = {field.argument: field for field in field_enum}
        if not values and not allow_empty:
            return None
        if not set(values).issubset(fields):
            return None
        # Enum сопоставляет имена аргументов инструмента с полями модели.
        return {fields[name].attribute: value for name, value in values.items()}

    def publish_update(self, data, make_changes):
        """Проверяет правку; отсутствие отметки оси сохраняет, остальные ошибки отклоняет."""
        if data == self.project.model_dump():
            return {"status": Status.OK, "message": VALUES_UNCHANGED}
        project, problems = validate_input(data)
        if self.has_errors(project, problems):
            errors = [problem for problem in problems if problem.level == Level.ERROR]
            if project is not None and all(problem.code == ProblemCode.MISSING_AXIS for problem in errors):
                change = make_changes(project)
                self.project, self.problems = project, problems
                self.changes.append(change)
                return self.release()
            return self.problem_response(Status.ERROR, problems, released=False, message=UPDATE_REJECTED_MESSAGE)
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
        response = {"status": result["status"], "released": True, "changes": asdict(change), "pdf": result["pdf"]}
        response.update({name: result[name] for name in ("assumptions_count", "assumptions") if name in result})
        if result["status"] == Status.WARNING:
            response["warnings"] = [check.message for check in result.get("checks", [])
                                    if check.status == Status.WARNING]
        return response

    def update_point(self, name, bends=None, **values):
        """Готовит правку точки вместе со всеми отводами и передаёт её в общую транзакцию выпуска."""
        bends = bends or []
        updates = self.parse_fields(values, PointField, allow_empty=bool(bends))
        if updates is None:
            return self.error_response(ProblemCode.FIELDS_REQUIRED, FIELDS_REQUIRED, name)
        if not all(isinstance(bend, dict) and {"at", "angle_deg"} <= bend.keys() for bend in bends):
            return self.error_response(ProblemCode.FIELDS_REQUIRED, BEND_FIELDS_REQUIRED, name)
        data = self.project.with_point(name, bends, **updates)
        if data is None:
            return self.error_response(ProblemCode.POINT_NOT_FOUND, POINT_NOT_FOUND, name)
        bend_points = [bend["at"] for bend in bends]
        return self.publish_update(data, lambda project: self.point_changes(name, project, bend_points=bend_points))

    def route_changes(self, title, values, project) -> ChangeSet:
        """Добавляет изменение длины и собирает перечень для всех листов."""
        before = calculate_route_geometry(self.project.points)["length_m"]
        after = calculate_route_geometry(project.points)["length_m"]
        self.add_value(values, LABEL_ROUTE_LENGTH, before, after)
        return ChangeSet(title, values, self.all_sheets())

    def point_values(self, before, after):
        """Возвращает изменения координат и отметок при правке, добавлении или удалении точки."""
        name = before.id if before is not None else after.id
        values = []
        for field in PointField:
            self.add_value(values, LABEL_POINT_VALUE.format(name=name, label=field.label),
                           getattr(before, field.attribute) if before is not None else None,
                           getattr(after, field.attribute) if after is not None else None, field.unit)
        return values

    def bend_values(self, at, project):
        """Возвращает изменение угла отвода, включая его добавление или удаление."""
        before = next((bend.angle_deg for bend in self.project.bends if bend.at == at), None)
        after = next((bend.angle_deg for bend in project.bends if bend.at == at), None)
        values = []
        self.add_value(values, LABEL_BEND_ANGLE.format(name=at), before, after, UNIT_DEGREE)
        return values

    def point_changes(self, name, project, title=TITLE_POINT_CHANGE, bend_points=()) -> ChangeSet:
        """Собирает изменения точки, отвода в ней и отводов из той же правки."""
        before = next((point for point in self.project.points if point.id == name), None)
        after = next((point for point in project.points if point.id == name), None)
        values = self.point_values(before, after)
        for at in dict.fromkeys([name, *bend_points]):
            values.extend(self.bend_values(at, project))
        return self.route_changes(title.format(name=name), values, project)

    def add_point(self, name, after, x, y, ground, axis, bend_angle=None):
        """Проверяет и выпускает вставку точки с необязательным отводом в ней."""
        point = {"id": name, "x": x, "y": y, "ground": ground, "axis": axis}
        data = self.project.with_added_point(after, point, bend_angle)
        if data is None:
            return self.error_response(ProblemCode.POINT_NOT_FOUND, POINT_NOT_FOUND, after)
        return self.publish_update(data, lambda project: self.point_changes(name, project, TITLE_ADD_POINT))

    def remove_point(self, name):
        """Проверяет и выпускает удаление точки вместе с её отводом."""
        data = self.project.without_point(name)
        if data is None:
            return self.error_response(ProblemCode.POINT_NOT_FOUND, POINT_NOT_FOUND, name)
        return self.publish_update(data, lambda project: self.point_changes(name, project, TITLE_REMOVE_POINT))

    def add_bend(self, at, angle_deg):
        """Проверяет и выпускает добавление отвода в существующей точке."""
        data = self.project.with_bend(at, angle_deg)
        if data is None:
            return self.error_response(ProblemCode.POINT_NOT_FOUND, POINT_NOT_FOUND, at)
        return self.publish_update(data, lambda project: self.route_changes(
            TITLE_ADD_BEND.format(name=at), self.bend_values(at, project), project))

    def remove_bend(self, at):
        """Проверяет и выпускает удаление отвода."""
        data = self.project.without_bend(at)
        if data is None:
            return self.error_response(ProblemCode.BEND_NOT_FOUND, BEND_NOT_FOUND, at)
        return self.publish_update(data, lambda project: self.route_changes(
            TITLE_REMOVE_BEND.format(name=at), self.bend_values(at, project), project))

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
        return self.route_changes(TITLE_PIPE_CHANGE, values, project)

    def change_profile_font(self, direction):
        size = ProfileStyle.font_step(self.font_size, direction)
        if size == self.font_size:
            return {"status": Status.OK, "message": VALUES_UNCHANGED}
        values = []
        self.add_value(values, LABEL_PROFILE_FONT, self.font_size, size, UNIT_MM)
        change = ChangeSet(TITLE_FONT_CHANGE, values, [self.documents.get(DocumentId.PROFILE)["short_title"]])
        return self.apply(self.project, change, size)
