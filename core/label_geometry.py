"""Общие оценки габаритов текста и пересечений в миллиметрах листа."""

from math import hypot

from config import drawing_settings as settings
from core.tables import text_width


def rectangles_overlap(bounds, other):
    """Проверяет пересечение внутренних областей двух прямоугольников."""
    return (bounds[0] < other[2] and bounds[2] > other[0]
            and bounds[1] < other[3] and bounds[3] > other[1])


def segment_crosses_rectangle(start, end, bounds):
    """Проверяет вход отрезка внутрь прямоугольника отсечением по двум осям."""
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return False
    entry, exit = 0.0, 1.0
    for origin, finish, minimum, maximum in [
        (start[0], end[0], bounds[0], bounds[2]),
        (start[1], end[1], bounds[1], bounds[3]),
    ]:
        direction = finish - origin
        if abs(direction) < settings.GEOMETRY_TOLERANCE_MM:
            if not minimum < origin < maximum:
                return False
        else:
            first = (minimum - origin) / direction
            second = (maximum - origin) / direction
            entry = max(entry, min(first, second))
            exit = min(exit, max(first, second))
            if entry >= exit:
                return False
    return entry < exit


def text_bounds(text, left, baseline, font_size, anchor="start"):
    """Возвращает оценку прямоугольника горизонтального текста в мм листа."""
    width = text_width(text, font_size)
    if anchor == "middle":
        left -= width / 2
    elif anchor == "end":
        left -= width
    return left, baseline - font_size, left + width, baseline


def labels_too_close(bounds, other):
    """Проверяет пересечение или зазор меньше заданного по оценкам габаритов текста."""
    horizontal_gap = max(other[0] - bounds[2], bounds[0] - other[2], 0)
    vertical_gap = max(other[1] - bounds[3], bounds[1] - other[3], 0)
    distance = hypot(horizontal_gap, vertical_gap)
    return distance + settings.GEOMETRY_TOLERANCE_MM < settings.LABEL_MIN_GAP_MM


def plan_label_width(name, station, coordinates):
    """Возвращает ширину блока подписей плана по общим размерам шрифтов, мм листа."""
    return max(text_width(name, settings.PLAN_FONT_SIZE_MM),
               text_width(station, settings.PLAN_FONT_SIZE_MM),
               text_width(coordinates, settings.PLAN_COORDINATE_FONT_SIZE_MM))
