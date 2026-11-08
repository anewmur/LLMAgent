from textwrap import wrap
from xml.sax.saxutils import escape

from core import drawing_settings as settings
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.paths import TEMPLATES_DIR
from core.formatting import render_template


TEMPLATE_PATH = TEMPLATES_DIR / "register_table.svg"


def wrap_text(text, width, font_size, break_long_words=True):
    """Возвращает строки текста, приближённо помещающиеся в ширину в мм листа."""
    characters = max(settings.TEXT_MIN_WRAP_CHARACTERS,
                     int(width / (font_size * settings.TEXT_CHARACTER_WIDTH_FACTOR)))
    lines = []
    for paragraph in str(text).splitlines():
        lines.extend(wrap(paragraph, characters, break_long_words=break_long_words) or [""])
    return lines or [""]


class TextBlock:
    """Текст с переносами в заданной ширине, размеры в миллиметрах."""

    def __init__(self, text, left, top, width, font_size=DEFAULT_FONT_SIZE_MM, break_long_words=True):
        """Сохраняет положение блока и переносит текст на строки."""
        self.lines = wrap_text(text, width, font_size, break_long_words)
        self.left, self.top, self.font_size = left, top, font_size

    def render(self, underline=False):
        """Возвращает SVG строк блока с необязательным подчёркиванием."""
        spans = [f'<tspan x="{self.left}" y="{self.top + index * settings.TEXT_LINE_STEP_MM}">{escape(line)}</tspan>'
                 for index, line in enumerate(self.lines)]
        svg = f'<text font-size="{self.font_size}">' + "".join(spans) + '</text>'
        if underline:
            for index, line in enumerate(self.lines):
                baseline = self.top + index * settings.TEXT_LINE_STEP_MM + 1
                svg += (f'<path d="M {self.left},{baseline} h {len(line) * self.font_size * 0.5}" '
                        f'stroke="black" stroke-width="{settings.TEXT_UNDERLINE_WIDTH_MM}"/>')
        return svg


class TableCell:
    """Тот же перенос текста, с размещением внутри ячейки таблицы."""

    def __init__(self, value, left, top, width, height, centered):
        """Переносит текст и сохраняет размеры и выравнивание ячейки."""
        self.lines = wrap_text(value, width - settings.TABLE_CELL_HORIZONTAL_PADDING_MM,
                               DEFAULT_FONT_SIZE_MM, break_long_words=not centered)
        self.left, self.top = left, top
        self.width, self.height, self.centered = width, height, centered

    def render(self):
        """Возвращает SVG строк, расположенных по центру высоты ячейки."""
        text_x = self.left + (self.width / 2 if self.centered else settings.TABLE_CELL_HORIZONTAL_PADDING_MM / 2)
        anchor = "middle" if self.centered else "start"
        elements = []
        for index, line in enumerate(self.lines):
            if not line:
                continue
            text_y = (self.top + self.height / 2 + settings.TABLE_CELL_BASELINE_OFFSET_MM
                      + (index - (len(self.lines) - 1) / 2) * settings.TABLE_CELL_LINE_STEP_MM)
            elements.append(f'<text x="{text_x:g}" y="{text_y:g}" text-anchor="{anchor}">{escape(line)}</text>')
        return "\n".join(elements)


class RegisterTable:
    """Ведомость: фиксированные графы, строки растут при переносах."""

    def __init__(self, headings, widths, rows):
        """Сохраняет заголовки, ширины граф и строки ведомости."""
        self.headings, self.widths, self.rows = headings, widths, rows

    def draw_row(self, values, row_top, height):
        """Возвращает SVG текста строки ведомости."""
        column_left = 0
        elements = []
        section = not values[0] and bool(values[1]) and not values[2]
        for column, (value, width) in enumerate(zip(values, self.widths)):
            padding = settings.TABLE_CELL_HORIZONTAL_PADDING_MM
            text = TextBlock(value, column_left + padding / 2, row_top, width - padding, DEFAULT_FONT_SIZE_MM)
            text.top = row_top + (height - (len(text.lines) - 1) * settings.TEXT_LINE_STEP_MM) / 2 + 1
            elements.append(text.render(underline=section and column == 1))
            column_left += width
        return "\n".join(elements)

    def row_height(self, row):
        """Возвращает высоту строки ведомости с учётом переноса текста."""
        counts = [len(wrap_text(value, width - settings.TABLE_CELL_HORIZONTAL_PADDING_MM, DEFAULT_FONT_SIZE_MM))
                  for value, width in zip(row, self.widths)]
        return max(settings.REGISTER_MIN_ROW_HEIGHT_MM,
                   max(counts) * settings.TEXT_LINE_STEP_MM + settings.REGISTER_ROW_PADDING_MM)

    def render(self):
        """Возвращает SVG ведомости с рамкой, сеткой и строками."""
        width = sum(self.widths)
        row_top = 15
        elements = [self.draw_row(self.headings, 0, 15)]
        borders = [f'M 0,15 H {width}']
        for row in self.rows:
            height = self.row_height(row)
            elements.append(self.draw_row(row, row_top, height))
            row_top += height
            borders.append(f'M 0,{row_top} H {width}')
        column_left = 0
        for cell_width in self.widths[:-1]:
            column_left += cell_width
            borders.append(f'M {column_left},0 V {row_top}')
        return render_template(TEMPLATE_PATH, {
            "font_family": settings.FONT_FAMILY,
            "width": width,
            "height": row_top,
            "grid": " ".join(borders),
            "contents": "\n".join(elements),
        })
