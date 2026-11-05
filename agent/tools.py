from core.calculations import calculate_route_length

TOOLS = [ {
        "type": "function",
        "function": {
            "name": "calculate_route_length",
            "description": (
                "Рассчитать общую длину трассы трубопровода (длину трубы) в метрах "
                "по точкам из входного файла. Используй, когда спрашивают длину "
                "или протяжённость трассы или трубы."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    }
]
HANDLERS = {"calculate_route_length": calculate_route_length}