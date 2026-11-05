from core.calculations import (
    calculate_route_length,
    calculate_pipe_levels,
    calculate_material_quantities,
)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_route_length",
            "description": (
                "Рассчитать общую длину трассы, длины участков и расстояния "
                "от начала трассы в метрах, уклоны участков и средний уклон "
                "всей трассы в промилле. Используй для вопросов о длинах, "
                "пикетаже и уклонах. Результат содержит все участки."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_pipe_levels",
            "description": (
                "Рассчитать высоту нижней поверхности трубы и глубину её "
                "заложения во всех точках трассы. Глубина измеряется от "
                "поверхности земли до нижней поверхности трубы. "
                "Все значения — в метрах. Используй для вопросов "
                "об отметках низа трубы и глубинах заложения."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_material_quantities",
            "description": (
                "Рассчитать количество трубы в метрах и отводов в штуках "
                "с группировкой по углу. Длина трубы считается по трассе "
                "в плане без запаса и вычета отводов. Используй для вопросов "
                "о количествах материалов. Это расчёт количеств, "
                "а не выпуск готовой спецификации."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


HANDLERS = {
    "calculate_route_length": calculate_route_length,
    "calculate_pipe_levels": calculate_pipe_levels,
    "calculate_material_quantities": calculate_material_quantities,
}
