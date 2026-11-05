# core/validate.py
from pydantic import ValidationError
from core.models import Project


def problem(level, where, message, blocks_length=False, blocks_quantities=False):
    return {
        "level": level,
        "where": where,
        "message": message,
        "blocks_length": blocks_length,
        "blocks_quantities": blocks_quantities,
    }


def validate_input(data):
    # 1. Структура и типы проверяет Pydantic
    try:
        project = Project.model_validate(data)
    except ValidationError as e:
        problems = []
        for err in e.errors():
            path = ".".join(str(part) for part in err["loc"])
            problems.append(problem(level="error", where=path, message=err["msg"]))
        return None, problems

    problems = []

    # 2. Отсутствующие отметки называем по имени точки
    for point in project.points:
        if point.axis is None:
            problems.append(problem(level="error", where=point.id,
                                    message="нет отметки оси трубы (axis)"))
        if point.ground is None:
            problems.append(problem(level="error", where=point.id,
                                    message="нет отметки земли (ground)"))

    # 3. Уникальность id точек
    ids = [point.id for point in project.points]
    for pid in set(ids):
        if ids.count(pid) > 1:
            problems.append(problem(
                level="error",
                where=pid,
                message="идентификатор точки повторяется",
                blocks_length=True,
            ))

    # 4. Отводы ссылаются на существующие точки
    for bend in project.bends:
        if bend.at not in ids:
            problems.append(problem(level="error", where=bend.at,
                                    message="отвод ссылается на несуществующую точку",
                                    blocks_quantities=True))

    bend_points = [bend.at for bend in project.bends]
    for pid in set(bend_points):
        if bend_points.count(pid) > 1:
            problems.append(problem(
                level="error", where=pid,
                message="в одной точке повторно указан отвод",
                blocks_quantities=True,
            ))

    # 5. Согласованность материалов
    if project.pipe.material != project.object.pipe_material:
        problems.append(problem(
            level="error",
            where="pipe",
            message=(f"материал трубы ({project.pipe.material}) не совпадает "
                     f"с описанием объекта ({project.object.pipe_material})"),
            blocks_quantities=True))

    # 6. Соседние точки должны задавать участок ненулевой длины в плане
    for start, end in zip(project.points, project.points[1:]):
        if start.x == end.x and start.y == end.y:
            problems.append(problem(
                level="error",
                where=f"{start.id}–{end.id}",
                message="соседние точки совпадают по X и Y: длина участка в плане равна нулю",
                blocks_length=True,
            ))

    return project, problems
