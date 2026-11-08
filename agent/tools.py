from enum import Enum

from core.drawing_settings import FONT_SIZES
from core.models import PipeField, PointField


class ToolName(str, Enum):
    """Имена инструментов в схемах API и таблице обработчиков."""

    CALCULATE_ROUTE_LENGTH = "calculate_route_length"
    CALCULATE_PIPE_LEVELS = "calculate_pipe_levels"
    CALCULATE_MATERIAL_QUANTITIES = "calculate_material_quantities"
    CHANGE_PROFILE_FONT = "change_profile_font"
    UPDATE_POINT = "update_point"
    UPDATE_PIPE = "update_pipe"
    RELEASE_DOCUMENTS = "release_documents"


def tool(name, description, properties=None, required=(), min_properties=None):
    """Возвращает описание инструмента с общей схемой аргументов."""
    parameters = {
        "type": "object",
        "properties": {} if properties is None else properties,
        "required": list(required),
    }
    if min_properties is not None:
        parameters["minProperties"] = min_properties
    # У явно заданных свойств запрещаем остальные ключи.
    if properties is not None:
        parameters["additionalProperties"] = False
    return {
        "type": "function",
        "function": {"name": name.value, "description": description, "parameters": parameters},
    }


TOOLS = [
    tool(
        ToolName.CALCULATE_ROUTE_LENGTH,
        (
            "Рассчитать общую длину трассы, длины участков и расстояния от начала трассы в "
            "метрах и уклоны участков в промилле. Используй для вопросов о длинах, пикетаже и "
            "уклонах. Результат содержит все участки."
        ),
    ),
    tool(
        ToolName.CALCULATE_PIPE_LEVELS,
        (
            "Рассчитать высоту нижней поверхности трубы и глубину её заложения во всех точках "
            "трассы. Глубина измеряется от поверхности земли до нижней поверхности трубы. Все "
            "значения — в метрах. Используй для вопросов об отметках низа трубы и глубинах "
            "заложения."
        ),
    ),
    tool(
        ToolName.CALCULATE_MATERIAL_QUANTITIES,
        (
            "Рассчитать количество трубы в метрах и отводов в штуках с группировкой по углу. "
            "Длина трубы считается по трассе в плане без запаса и вычета отводов. Используй для "
            "вопросов о количествах материалов. Это расчёт количеств, а не выпуск готовой "
            "спецификации."
        ),
    ),
    tool(
        ToolName.CHANGE_PROFILE_FONT,
        (
            "Увеличить или уменьшить базовый шрифт профиля на одну ступень ряда "
            f'{", ".join(f"{size:g}" for size in FONT_SIZES)} мм и перевыпустить комплект. '
            "direction=1 — увеличить, direction=-1 — "
            "уменьшить. Если выбранный размер не помещается в таблицу, инструмент вернёт "
            "причину."
        ),
        properties={"direction": {"type": "integer", "enum": [-1, 1]}},
        required=("direction",),
    ),
    tool(
        ToolName.UPDATE_POINT,
        (
            "Изменить точку текущей трассы и перевыпустить комплект. name — имя точки, x и y — "
            "координаты в плане, z — отметка оси трубы, в метрах. Неуказанные поля остаются "
            "прежними. Явный null — попытка удалить значение. При ошибке проект и документы не "
            "меняются; уточни данные у пользователя. При warning изменение принято и комплект "
            "опубликован; сообщи предупреждения."
        ),
        properties={
            "name": {"type": "string"},
            **{field.argument: {"type": ["number", "null"]} for field in PointField},
        },
        required=("name",),
    ),
    tool(
        ToolName.UPDATE_PIPE,
        (
            "Изменить материал или размеры трубы текущей трассы и перевыпустить комплект. "
            "Укажите хотя бы один параметр; "
            "неуказанные поля остаются прежними. Материал одновременно обновляется в "
            "описании объекта. При ошибке проект и документы не меняются; уточни данные "
            "у пользователя. После успеха покажи перечень изменений. При warning изменение "
            "принято и комплект опубликован; сообщи предупреждения."
        ),
        properties={
            field.argument: {
                "type": field.json_type,
                "description": f"{field.label}, {field.unit}" if field.unit else field.label,
            }
            for field in PipeField if field != PipeField.STANDARD
        },
        min_properties=1,
    ),
    tool(
        ToolName.RELEASE_DOCUMENTS,
        (
            "Перевыпустить комплект документов по текущим данным сессии."
        ),
        properties={},
    ),
]
