"""Общий выбор изображения трубы и полка линии-выноски."""

from xml.sax.saxutils import escape

from core import drawing_settings as settings
from core.formatting import format_pipe_value, render_template
from core.paths import TEMPLATES_DIR
from core.tables import text_width


def pipe_line_count(outer_diameter_mm, scale):
    """Возвращает число линий по диаметру на листе: ГОСТ 21.206, п. 3.5."""
    return 2 if outer_diameter_mm / scale >= settings.PIPE_TWO_LINE_THRESHOLD_MM else 1


def pipe_size_text(pipe):
    """Возвращает наружный диаметр и стенку без единиц: ГОСТ 21.206, п. 3.11."""
    return f"⌀{format_pipe_value(pipe.outer_diameter_mm)}×{format_pipe_value(pipe.wall_mm)}"


def pipe_shelf_width(pipe):
    """Возвращает ширину полки по размерной надписи и боковым отступам, мм листа."""
    return max(settings.PIPE_SHELF_WIDTH_MM,
               text_width(pipe_size_text(pipe), settings.PIPE_LABEL_FONT_SIZE_MM)
               + 2 * settings.PIPE_SHELF_PADDING_MM)


def pipe_leader(pipe, target, shelf, direction=1):
    """Возвращает общую для плана и профиля полку с обозначением и размером трубы."""
    target_x, target_y = target
    shelf_x, shelf_y = shelf
    size = pipe_size_text(pipe)
    font_size = settings.PIPE_LABEL_FONT_SIZE_MM
    width = pipe_shelf_width(pipe)
    left, right = sorted((shelf_x, shelf_x + direction * width))
    if left <= target_x <= right:
        shelf_x = target_x + direction * settings.PIPE_SHELF_SIDE_OFFSET_MM
    elif abs(target_x - (shelf_x + direction * width)) < abs(target_x - shelf_x):
        shelf_x += direction * width
        direction = -direction
    end_x = shelf_x + direction * width
    left, right = sorted((shelf_x, end_x))
    return render_template(TEMPLATES_DIR / "pipe_leader.svg", {
        "target_x": target_x, "target_y": target_y, "shelf_x": shelf_x, "shelf_y": shelf_y,
        "end_x": end_x, "center_x": (shelf_x + end_x) / 2,
        "top_y": shelf_y - settings.PIPE_SHELF_TEXT_GAP_MM,
        "bottom_y": shelf_y + font_size + settings.PIPE_SHELF_TEXT_GAP_MM,
        "left": left, "right": right,
        "bounds_top": shelf_y - settings.PIPE_SHELF_TEXT_GAP_MM - font_size,
        "bounds_bottom": shelf_y + settings.PIPE_SHELF_TEXT_GAP_MM + font_size,
        "font_size": font_size, "font_family": settings.FONT_FAMILY,
        "line_width": settings.PIPE_LEADER_LINE_WIDTH_MM,
        "network": escape(settings.NETWORK_CODE), "size": escape(size),
    })


def leader_crosses_shelf_text(label):
    """Проверяет только наклонный отрезок выноски против двух текстов полки."""
    from core.label_geometry import text_bounds, segment_crosses_rectangle
    path = next(child for child in label if child.get("data-kind") == "pipe-leader")
    tokens = path.get("d").split()
    start, end = [tuple(map(float, value.split(","))) for value in (tokens[1], tokens[3])]
    size = float(label.get("font-size"))
    for child in label:
        if child.get("data-kind") in ("pipe-network", "pipe-size"):
            bounds = text_bounds(child.text or "", float(child.get("x")), float(child.get("y")),
                                 size, child.get("text-anchor", "start"))
            if segment_crosses_rectangle(start, end, bounds):
                return True
    return False
