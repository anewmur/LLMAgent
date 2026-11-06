from xml.sax.saxutils import escape
from textwrap import wrap
from string import Template
import json
from pathlib import Path
import os
from reportlab.graphics import renderPDF
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from svglib.svglib import svg2rlg


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "sheet.svg"
PAPER_SIZES = {"A3": (420, 297), "A2": (594, 420)}


class Sheet:
    """Лист A3 или A2 с основной надписью по постоянному SVG-макету.

    Эталон сетки формы 3 (185×55 мм): dell4valt/gost_template,
    «SVG/Форма 3/Форма 3 [A3-альбомный].svg»:
    https://raw.githubusercontent.com/dell4valt/gost_template/master/SVG/%D0%A4%D0%BE%D1%80%D0%BC%D0%B0%203/%D0%A4%D0%BE%D1%80%D0%BC%D0%B0%203%20%5BA3-%D0%B0%D0%BB%D1%8C%D0%B1%D0%BE%D0%BC%D0%BD%D1%8B%D0%B9%5D.svg
    """

    def __init__(self, designation, object_name, title, number, total, paper="A3"):
        if paper not in PAPER_SIZES:
            raise ValueError("Поддерживаются форматы A3 и A2.")
        self.width, self.height = PAPER_SIZES[paper]
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
        return template.substitute(
            width=self.width, height=self.height,
            frame_width=self.width - 25, frame_height=self.height - 10,
            stamp_x=self.width - 190, stamp_y=self.height - 60,
            center_x=(self.width + 15) / 2,
            designation=escape(str(self.designation)),
            object_name=escape(str(self.object_name)),
            title=self.title_svg(),
            number=escape(str(self.number)),
            total=escape(str(self.total)),
        )


def create_sheet(designation, object_name, title, number, total):
    return Sheet(designation, object_name, title, number, total).render()


def svg_to_pdf(svg_path, pdf_path):
    """Преобразовать SVG в PDF, встроив Arial для отображения кириллицы."""
    font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf"
    pdfmetrics.registerFont(TTFont("Arial", str(font_path)))
    pdfmetrics.registerFontFamily("Arial", normal="Arial")

    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        raise ValueError("Не удалось прочитать SVG")
    renderPDF.drawToFile(drawing, str(pdf_path))


if __name__ == "__main__":
    root = Path(__file__).resolve().parent.parent
    data = json.loads((root / "input" / "input.json").read_text(encoding="utf-8"))
    object_info = data["object"]

    sheet = Sheet(
        designation=object_info["project_code"] + "-НВ",
        object_name=object_info["name"],
        title="Лист основы",
        number=1,
        total=3,
    )
    svg = sheet.render()

    output = root / "output"
    (output / "pdf").mkdir(parents=True, exist_ok=True)
    svg_path = output / "sheet_a3.svg"
    pdf_path = output / "pdf" / "sheet_a3.pdf"
    svg_path.write_text(svg, encoding="utf-8")
    svg_to_pdf(svg_path, pdf_path)
    print(svg_path)
    print(pdf_path)
