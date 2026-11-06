from decimal import Decimal, ROUND_HALF_UP


def format_number(value):
    if value is None:
        return "—"

    number = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if number == 0:
        number = abs(number)  # Чтобы не было отрицательного ноля.
    return f"{number:.2f}".replace(".", ",")


def format_station(distance):
    if distance is None:
        return "—"

    distance = Decimal(str(distance)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    station = int(distance // 100)
    meters = distance % 100
    return f"ПК {station}+{meters:05.2f}".replace(".", ",")
