FONT_SIZES = (2.5, 3.5, 5, 7, 10, 14)


class ProfileStyle:
    """Базовый размер из ряда; названия в 1,5–2 раза крупнее."""

    def __init__(self, base_size=3.5):
        if isinstance(base_size, bool) or base_size not in FONT_SIZES:
            raise ValueError("Размер шрифта: 2.5; 3.5; 5; 7; 10; 14 мм.")
        self.base_size = base_size
        self.title_size = next((s for s in FONT_SIZES if 1.5 * base_size <= s <= 2 * base_size), None)
        if self.title_size is None:
            raise ValueError("Для этого базового размера в разрешённом ряду нет названия в 1,5–2 раза крупнее.")

    @staticmethod
    def font_step(size, direction):
        if isinstance(size, bool) or size not in FONT_SIZES:
            raise ValueError("Размер шрифта отсутствует в разрешённом ряду.")
        if isinstance(direction, bool) or direction not in (-1, 1):
            raise ValueError("Шаг шрифта должен быть +1 или -1.")
        index = FONT_SIZES.index(size) + direction
        return FONT_SIZES[max(0, min(index, len(FONT_SIZES) - 1))]

    def check_table(self):
        if self.base_size * 4.5 > 20:
            raise ValueError(
                f"Шрифт {self.base_size:g} мм не помещается в фиксированные строки пикетов таблицы. "
                "Уменьшите шрифт; прежний лист сохранён."
            )
