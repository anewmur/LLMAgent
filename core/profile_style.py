from config import drawing_settings as settings
from config.drawing_settings import DEFAULT_FONT_SIZE_MM, FONT_SIZES
from core.formatting import format_pipe_value, format_station
from core.tables import text_width


class ProfileStyle:
    """Базовый размер из ряда; названия в 1,5–2 раза крупнее."""

    def __init__(self, base_size=DEFAULT_FONT_SIZE_MM):
        """Проверяет базовый размер и выбирает размер названий в разрешённом ряду."""
        if isinstance(base_size, bool) or base_size not in FONT_SIZES:
            allowed_sizes = "; ".join(f"{size:g}" for size in FONT_SIZES)
            raise ValueError(f"Размер шрифта: {allowed_sizes} мм.")
        self.base_size = base_size
        self.title_size = next((
            size for size in FONT_SIZES
            if settings.TITLE_FONT_MIN_FACTOR * base_size <= size <= settings.TITLE_FONT_MAX_FACTOR * base_size
        ), None)
        if self.title_size is None:
            raise ValueError(
                "Для этого базового размера в разрешённом ряду нет названия в "
                f"{format_pipe_value(settings.TITLE_FONT_MIN_FACTOR)}–{format_pipe_value(settings.TITLE_FONT_MAX_FACTOR)} раза крупнее."
            )

    @staticmethod
    def font_step(size, direction):
        """Возвращает соседний допустимый размер шрифта, оставаясь в границах ряда."""
        if isinstance(size, bool) or size not in FONT_SIZES:
            raise ValueError("Размер шрифта отсутствует в разрешённом ряду.")
        if isinstance(direction, bool) or direction not in (-1, 1):
            raise ValueError("Шаг шрифта должен быть +1 или -1.")
        index = FONT_SIZES.index(size) + direction
        return FONT_SIZES[max(0, min(index, len(FONT_SIZES) - 1))]

    def check_table(self):
        """Проверяет, помещается ли вертикальная подпись пикета в свою строку."""
        if text_width(format_station(0), self.base_size) > settings.PROFILE_STATION_TEXT_HEIGHT_MM:
            raise ValueError(
                f"Шрифт {self.base_size:g} мм не помещается в фиксированные строки пикетов таблицы. "
                "Уменьшите шрифт; прежний лист сохранён."
            )
