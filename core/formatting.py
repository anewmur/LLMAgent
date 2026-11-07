from decimal import Decimal, ROUND_HALF_UP


def format_number(value):
    if value is None:
        return "—"

    number = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if number == 0:
        number = abs(number)  # Чтобы не было отрицательного ноля.
    return f"{number:.2f}".replace(".", ",")


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
