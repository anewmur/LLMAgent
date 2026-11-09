from textwrap import wrap
from xml.sax.saxutils import escape

from svglib.fonts import register_font
from svglib.svglib import svg2rlg

from core import drawing_settings as settings
from core.paths import FONT_PATH, TEMPLATES_DIR
from core.formatting import render_template


TEMPLATE_PATH = TEMPLATES_DIR / "sheet.svg"


class Sheet:
    """Лист A3 альбомный с рамкой и основной надписью из одного шаблона.

    Эталон сетки формы 3 (185×55 мм): dell4valt/gost_template,
    «SVG/Форма 3/Форма 3 [A3-альбомный].svg»:
    https://raw.githubusercontent.com/dell4valt/gost_template/master/SVG/%D0%A4%D0%BE%D1%80%D0%BC%D0%B0%203/%D0%A4%D0%BE%D1%80%D0%BC%D0%B0%203%20%5BA3-%D0%B0%D0%BB%D1%8C%D0%B1%D0%BE%D0%BC%D0%BD%D1%8B%D0%B9%5D.svg
    """

    width, height = settings.SHEET_WIDTH_MM, settings.SHEET_HEIGHT_MM
    paper = "A3"

    def __init__(self, designation="", object_name="", title="", total=""):
        """Сохраняет реквизиты; номер листа задаётся отдельно из состава комплекта."""
        self.designation = designation
        self.object_name = object_name
        self.title = title
        self.number = ""
        self.total = total

    def title_svg(self):
        """Возвращает SVG-строки названия, перенесённые внутри основной надписи."""
        lines = wrap(str(self.title), width=settings.SHEET_TITLE_WRAP_CHARACTERS) or [""]
        middle_line = (len(lines) - 1) / 2
        elements = []
        for index, line in enumerate(lines):
            baseline_y = settings.SHEET_TITLE_BASELINE_Y_MM + (index - middle_line) * settings.SHEET_TITLE_LINE_STEP_MM
            elements.append(f'<tspan x="{settings.SHEET_TITLE_CENTER_X_MM:g}" '
                            f'y="{baseline_y:g}">{escape(line)}</tspan>')
        return "".join(elements)

    def render(self, body=""):
        """Возвращает SVG-лист с рамкой и заполненной основной надписью."""
        return render_template(TEMPLATE_PATH, {
            "body": body + "\n" if body else "",
            "sheet_width": self.width,
            "sheet_height": self.height,
            "frame_left": settings.SHEET_FRAME_LEFT_MM,
            "frame_top": settings.SHEET_FRAME_TOP_MM,
            "frame_width": self.width - settings.SHEET_FRAME_HORIZONTAL_MARGINS_MM,
            "frame_height": self.height - settings.SHEET_FRAME_VERTICAL_MARGINS_MM,
            "stamp_left": self.width - settings.SHEET_STAMP_RIGHT_OFFSET_MM,
            "stamp_top": self.height - settings.SHEET_STAMP_BOTTOM_OFFSET_MM,
            "stamp_width": settings.SHEET_STAMP_WIDTH_MM,
            "stamp_height": settings.SHEET_STAMP_HEIGHT_MM,
            "sheet_number_x": f"{settings.SHEET_NUMBER_X_MM:g}",
            "sheet_total_x": f"{settings.SHEET_TOTAL_X_MM:g}",
            "sheet_number_y": f"{settings.SHEET_NUMBER_Y_MM:g}",
            "training_label": escape(settings.TRAINING_LABEL),
            "training_x": settings.SHEET_TRAINING_X_MM, "training_y": settings.SHEET_TRAINING_Y_MM,
            "training_size": settings.SHEET_TRAINING_FONT_MM,
            "font_family": settings.FONT_FAMILY,
            "designation": escape(str(self.designation)),
            "object_name": escape(str(self.object_name)),
            "title": self.title_svg(),
            "number": escape(str(self.number)),
            "total": escape(str(self.total)),
        })


def svg_drawing(svg_path):
    """Возвращает SVG-рисунок с зарегистрированным шрифтом для страницы PDF."""
    register_font(settings.FONT_FAMILY, str(FONT_PATH))
    drawing = svg2rlg(str(svg_path))
    if drawing is None:
        raise ValueError("Не удалось прочитать SVG")
    return drawing
