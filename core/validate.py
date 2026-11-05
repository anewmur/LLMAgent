# core/validate.py
from pydantic import ValidationError
from core.models import Project


def problem(level, where, message):
    return {"level": level, "where": where, "message": message}


def validate_input(data):
    # 1. Структура и типы
    try:
        project = Project.model_validate(data)
    except ValidationError as e:
        problems = []
        for err in e.errors():
            where = ".".join(str(part) for part in err["loc"])
            problems.append(problem("error", where, err["msg"]))
        return None, problems

    problems = []

    # 2. Отсутствующие отметки называем по имени точки
    for point in project.points:
        if point.axis is None:
            problems.append(problem("error", point.id, "нет отметки оси трубы (axis)"))
        if point.ground is None:
            problems.append(problem("error", point.id, "нет отметки земли (ground)"))

    # 3. Уникальность id точек
    ids = [point.id for point in project.points]
    for pid in set(ids):
        if ids.count(pid) > 1:
            problems.append(problem("error", pid, "идентификатор точки повторяется"))

    # 4. Отводы ссылаются на существующие точки
    for b in project.bends:
        if b.at not in ids:
            problems.append(problem("error", b.at, "отвод ссылается на несуществующую точку"))

    # 5. Согласованность материалов
    if project.pipe.material != project.object.pipe_material:
        problems.append(problem(
            "error", "pipe",
            f"материал трубы ({project.pipe.material}) не совпадает "
            f"с описанием объекта ({project.object.pipe_material})"))
        
    return project, problems