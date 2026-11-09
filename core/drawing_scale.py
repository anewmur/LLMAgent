"""Общий выбор крупнейшего масштаба, при котором вид помещается в поле листа."""

from core import drawing_settings as settings
from core.calculations import calculate_route_geometry
from core.formatting import format_number, format_station, format_point_title
from core.label_geometry import plan_label_width


def choose_scale(extents_m, available_mm, scales, error_message):
    """Возвращает первый подходящий знаменатель из возрастающего ряда масштабов."""
    for scale in scales:
        if scale <= 0:
            raise ValueError(settings.SCALE_POSITIVE_ERROR)
        if all(extent * 1000 / scale <= available for extent, available in zip(extents_m, available_mm)):
            return scale
    raise ValueError(error_message)


def choose_plan_scale(project, scale=None):
    """Учитывает габариты трассы и блоков, которые размещаются внутри поля с выносками."""
    width = max(point.x for point in project.points) - min(point.x for point in project.points)
    height = max(point.y for point in project.points) - min(point.y for point in project.points)
    available_width = settings.SHEET_WIDTH_MM - settings.PLAN_FIELD_HORIZONTAL_MARGINS_MM
    error_message = settings.PLAN_FIT_ERROR if scale is None else settings.PLAN_SCALE_FIT_ERROR.format(scale=scale)
    if max_plan_label_width(project) > available_width:
        raise ValueError(error_message)
    return choose_scale((width, height), (available_width, settings.PLAN_FIELD_HEIGHT_MM),
                        settings.PLAN_SCALES if scale is None else (scale,), error_message)


def max_plan_label_width(project):
    """Оценивает ширину тех же имён, пикетов и координат, которые рисует план."""
    geometry = calculate_route_geometry(project.points)
    stations = [0] + [section["cumsum_dist_m"] for section in geometry["sections"]]
    bends = {bend.at: bend for bend in project.bends}
    bend_names = project.bend_names()
    return max(plan_label_width(
        format_point_title(point.id, bends.get(point.id), bend_names.get(point.id)),
        format_station(station), f"X={format_number(point.x)}, Y={format_number(point.y)}")
        for point, station in zip(project.points, stations))
