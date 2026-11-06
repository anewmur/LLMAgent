from xml.sax.saxutils import escape
from textwrap import wrap
from string import Template
from pathlib import Path
import os
from reportlab.graphics import renderPDF
from svglib.svglib import svg2rlg
from svglib.fonts import register_font


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "sheet.svg"


class Sheet:
    """Лист A3 альбомный с рамкой и основной надписью из одного шаблона.

    Эталон сетки формы 3 (185×55 мм): dell4valt/gost_template,
    «SVG/Форма 3/Форма 3 [A3-альбомный].svg»:
    https://raw.githubusercontent.com/dell4valt/gost_template/master/SVG/%D0%A4%D0%BE%D1%80%D0%BC%D0%B0%203/%D0%A4%D0%BE%D1%80%D0%BC%D0%B0%203%20%5BA3-%D0%B0%D0%BB%D1%8C%D0%B1%D0%BE%D0%BC%D0%BD%D1%8B%D0%B9%5D.svg
    """

    width, height = 420, 297
    paper = "A3"

    def __init__(self, designation="", object_name="", title="", number="", total=""):
        self.designation = designation
        self.object_name = object_name
        self.title = title
        self.number = number
        self.total = total

    def title_svg(self):
        lines = wrap(str(self.title), width=34) or [""]
        return "".join(
            f'<tspan x="100" y="{35.5 + (i - (len(lines) - 1) / 2) * 4.5:g}">{escape(line)}</tspan>'
            for i, line in enumerate(lines)
        )

    def render(self):
        template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
        return template.safe_substitute(
            designation=escape(str(self.designation)),
            object_name=escape(str(self.object_name)),
            title=self.title_svg(),
            number=escape(str(self.number)),
            total=escape(str(self.total)),
        )




def svg_to_pdf(svg_path, pdf_path):
    """Преобразовать SVG в PDF с явной картой шрифтов и кириллицей."""
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
    symbol_path = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "DejaVuSans.ttf"
    register_font("Arial", str(font_path if font_path.exists() else symbol_path))
    register_font("DejaVu Sans", str(symbol_path))

    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        raise ValueError("Не удалось прочитать SVG")
    renderPDF.drawToFile(drawing, str(pdf_path))
