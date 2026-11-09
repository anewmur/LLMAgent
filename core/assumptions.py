"""Единая загрузка полных и кратких допущений из конфигурации."""

from dataclasses import dataclass

from core import drawing_settings as settings
from core.formatting import format_pipe_value
from core.pipe_drawing import pipe_line_count


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
    threshold = settings.PIPE_TWO_LINE_THRESHOLD_MM
    pipe_lines = pipe_line_count(diameter, vertical_scale)
    values = {
        "network_code": settings.NETWORK_CODE,
        "axis_note": config["axis_notes"][bool(settings.DRAW_PIPE_AXIS and pipe_line_count(diameter, settings.PLAN_SCALE) == 2)],
        "insulation": project.pipe.insulation or config["profile"]["default_insulation"],
        "diameter": format_pipe_value(diameter), "vertical_scale": format_pipe_value(vertical_scale),
        "on_paper": format_pipe_value(on_paper),
        "profile_two_line_threshold_mm": format_pipe_value(threshold),
        "comparison": "≥" if pipe_lines == 2 else "<",
        "pipe_lines": pipe_lines,
        "bend_radius_factor": format_pipe_value(settings.BEND_RADIUS_FACTOR),
        "profile_gap": format_pipe_value(settings.PROFILE_LOWEST_PIPE_GAP_MM),
        "slope_tolerance": format_pipe_value(settings.SLOPE_INTEGER_TOLERANCE),
        "pipe_lines_text": config["pipe_lines_text"][pipe_lines],
    }
    return [Assumption(item["id"], item["full"].format(**values).strip(), item["short"].format(**values).strip(), item.get("key", False))
            for item in config["assumptions"]
            if item.get("plan_lines") in (None, pipe_line_count(diameter, settings.PLAN_SCALE))]
