TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "calculate_route_length",
            "description": (
                "Рассчитать общую длину трассы, длины участков и расстояния "
                "от начала трассы в метрах и уклоны участков в промилле. "
                "Используй для вопросов о длинах, "
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
    {
        "type": "function",
        "function": {
            "name": "change_profile_font",
            "description": (
                "Увеличить или уменьшить базовый шрифт профиля на одну ступень "
                "ряда 2.5, 3.5, 5, 7, 10, 14 мм и перевыпустить комплект. "
                "direction=1 — увеличить, direction=-1 — уменьшить. "
                "Если выбранный размер не помещается в таблицу, инструмент вернёт причину."
            ),
            "parameters": {
                "type": "object",
                "properties": {"direction": {"type": "integer", "enum": [-1, 1]}},
                "required": ["direction"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_point",
            "description": (
                "Изменить точку текущей трассы и перевыпустить комплект. "
                "name — имя точки, x и y — координаты в плане, z — отметка оси трубы, в метрах. "
                "Неуказанные поля остаются прежними. Явный null — попытка удалить значение. "
                "Если проверка не пройдена, проект и документы не меняются; уточни данные у пользователя."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "x": {"type": ["number", "null"]},
                    "y": {"type": ["number", "null"]},
                    "z": {"type": ["number", "null"]},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "release_documents",
            "description": "Перевыпустить комплект документов по текущим данным сессии.",
            "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
        },
    },

]
