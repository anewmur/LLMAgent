from pathlib import Path
from core.calculations import calculate_route_length, INPUT_PATH

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


BAD_FILE = INPUT_PATH.parent / "input_no_p3_axis.json"
HANDLERS = {"calculate_route_length": lambda: calculate_route_length(BAD_FILE)}