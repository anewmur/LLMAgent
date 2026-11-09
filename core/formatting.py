from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from string import Template

from core import drawing_settings as settings


def format_number(value, places=2):
    if value is None:
        return "—"

    number = Decimal(str(value)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if number == 0:
        number = abs(number)  # Чтобы не было отрицательного ноля.
    return f"{number:.{places}f}".replace(".", ",")


def format_pipe_value(value):
    """Возвращает число с десятичной запятой без незначащих нулей для подписи трубы."""
    return format_number(value).rstrip("0").rstrip(",")


def format_change_value(value):
    """Возвращает текст изменения без преобразования, а число — с принятым округлением."""
    return value if isinstance(value, str) else format_number(value)


def format_station(distance):
    if distance is None:
        return "—"

    distance = Decimal(str(distance)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    station = int(distance // 100)
    meters = distance % 100
    return f"ПК {station}+{meters:05.2f}".replace(".", ",")


def render_template(path, values):
    """Читает шаблон в UTF-8 и возвращает текст с безопасной подстановкой значений."""
    return Template(Path(path).read_text(encoding="utf-8")).safe_substitute(values)


def format_slope(value):
    """Возвращает модуль уклона целым при малом отклонении, иначе с одним знаком."""
    if value is None:
        return "—"
    slope = abs(Decimal(str(value)))
    integer = slope.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    places = 0 if abs(slope - integer) <= Decimal(str(settings.SLOPE_INTEGER_TOLERANCE)) else 1
    return format_number(slope, places)
