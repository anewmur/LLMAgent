"""Единая загрузка полных и кратких допущений из конфигурации."""

from dataclasses import dataclass

from core import drawing_settings as settings
from core.formatting import format_pipe_value


@dataclass(frozen=True)
class Assumption:
    """Одна оговорка с идентификатором и двумя вариантами текста."""

    id: str
    full: str
    short: str
    key: bool = False


def load_assumptions(config, project, vertical_scale) -> list[Assumption]:
    """Подставляет данные проекта в YAML-шаблоны, сохраняя их порядок."""
    diameter = project.pipe.outer_diameter_mm
    on_paper = diameter / vertical_scale
    threshold = settings.PROFILE_TWO_LINE_THRESHOLD_MM
    pipe_lines = 2 if on_paper >= threshold else 1
    values = {
        "network_code": settings.NETWORK_CODE,
        "diameter": format_pipe_value(diameter), "vertical_scale": format_pipe_value(vertical_scale),
        "on_paper": format_pipe_value(on_paper),
        "profile_two_line_threshold_mm": format_pipe_value(threshold),
        "comparison": "≥" if on_paper >= threshold else "<",
        "pipe_lines": pipe_lines,
        "pipe_lines_text": config["pipe_lines_text"][pipe_lines],
    }
    return [Assumption(item["id"], item["full"].format(**values), item["short"].format(**values), item.get("key", False))
            for item in config["assumptions"]]
