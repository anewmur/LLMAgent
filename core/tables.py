from pathlib import Path
from string import Template
from textwrap import wrap
from xml.sax.saxutils import escape


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "register_table.svg"


class TextBlock:
    """Текст с переносами в заданной ширине, размеры в миллиметрах."""

    def __init__(self, text, x, y, width, font_size=3.5, break_long_words=True):
        self.lines = wrap(str(text), max(4, int(width / (font_size * 0.55))),
                          break_long_words=break_long_words) or [""]
        self.x, self.y, self.font_size = x, y, font_size

    def render(self, underline=False):
        spans = [f'<tspan x="{self.x}" y="{self.y + i * 4.5}">{escape(line)}</tspan>'
                 for i, line in enumerate(self.lines)]
        svg = f'<text font-size="{self.font_size}">' + "".join(spans) + '</text>'
        if underline:
            for i, line in enumerate(self.lines):
                svg += (f'<path d="M {self.x},{self.y + i * 4.5 + 1} h {len(line) * self.font_size * 0.5}" '
                        'stroke="black" stroke-width="0.15"/>')
        return svg


class TableCell(TextBlock):
    """Тот же перенос текста, с размещением внутри ячейки таблицы."""

    def __init__(self, value, x, y, width, height, centered):
        super().__init__(value, x, y, width - 4, 3.5, break_long_words=not centered)
        self.width, self.height, self.centered = width, height, centered

    def render(self):
        x = self.x + self.width / 2 if self.centered else self.x + 2
        anchor = "middle" if self.centered else "start"
        elements = []
        for i, line in enumerate(self.lines):
            if not line:
                continue
            y = self.y + self.height / 2 + 1.2 + (i - (len(self.lines) - 1) / 2) * 4
            elements.append(f'<text x="{x:g}" y="{y:g}" text-anchor="{anchor}">{escape(line)}</text>')
        return "\n".join(elements)


class RegisterTable:
    """Ведомость: фиксированные графы, строки растут при переносах."""

    def __init__(self, headings, widths, rows):
        self.headings, self.widths, self.rows = headings, widths, rows

    def draw_row(self, values, y, height):
        x = 0
        elements = []
        section = not values[0] and bool(values[1]) and not values[2]
        for column, (value, width) in enumerate(zip(values, self.widths)):
            text = TextBlock(value, x + 2, y, width - 4, 3.5)
            text.y = y + (height - (len(text.lines) - 1) * 4.5) / 2 + 1
            elements.append(text.render(underline=section and column == 1))
            x += width
        return "\n".join(elements)

    def row_height(self, row):
        counts = [len(TextBlock(value, 0, 0, width - 4, 3.5).lines)
                  for value, width in zip(row, self.widths)]
        return max(8, max(counts) * 4.5 + 3)

    def render(self):
        width = sum(self.widths)
        y = 15
        elements = [self.draw_row(self.headings, 0, 15)]
        borders = [f'M 0,15 H {width}']
        for row in self.rows:
            height = self.row_height(row)
            elements.append(self.draw_row(row, y, height))
            y += height
            borders.append(f'M 0,{y} H {width}')
        x = 0
        for cell_width in self.widths[:-1]:
            x += cell_width
            borders.append(f'M {x},0 V {y}')
        return Template(TEMPLATE_PATH.read_text(encoding="utf-8")).safe_substitute(
            width=width, height=y, grid=" ".join(borders), contents="\n".join(elements),
        )
