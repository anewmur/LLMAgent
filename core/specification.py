from pathlib import Path
import csv

from core import drawing_settings as settings
from core.calculations import calculate_material_quantities
from core.formatting import format_number, format_pipe_value
from core.models import Project, SpecificationColumn, UNIT_M, UNIT_PIECE
from core.paths import TEMPLATES_DIR
from core.sheet import Sheet
from core.tables import TableCell
from core.templates import render_template


# форма 1 ГОСТ 21.110-2013, ширины граф в миллиметрах.
HEADERS = [
    "Поз.", "Наименование и техническая характеристика",
    "Тип, марка, обозначение документа, опросного листа",
    "Код продукции", "Поставщик", "Ед. измерения", "Количество",
    "Масса 1 ед., кг", "Примечание",
]
# Явный перенос длинного заголовка на листе; в CSV остаётся полное имя графы.
HEADER_LINE_BREAKS = {"Количество": "Коли-\nчество"}
WIDTHS = [20, 130, 60, 35, 45, 20, 20, 25, 40]
# Графы «Наименование» и «Примечание» выравниваются влево; индексы отсчитываются от нуля.
LEFT_ALIGNED_COLUMNS = (SpecificationColumn.NAME, SpecificationColumn.NOTE)
TEMPLATE_PATH = TEMPLATES_DIR / "specification.svg"


class SpecificationDrawing:
    """Спецификация по проверенному проекту и постоянному SVG-макету."""

    def __init__(self, project: Project, document):
        """Готовит лист и строки спецификации по проверенному проекту."""
        self.project = project
        self.sheet = Sheet(document["designation"], project.object.name,
                           document["title"], total=document["total"])
        self.quantities = calculate_material_quantities(project)
        self.rows = self.build_rows()

    def build_rows(self):
        """Один список строк для CSV и SVG; количества уже рассчитаны."""
        pipe = self.quantities["pipe"]
        diameter = format_pipe_value(pipe["outer_diameter_mm"])
        wall = format_pipe_value(pipe["wall_mm"])
        sdr = format_pipe_value(pipe["sdr"])
        rows = []

        # изделия перед трубой; отводы в штуках.
        # ГОСТ 21.704-2011, п. 7.4: исключение не применяется — отводы заданы в ТЗ.
        for bend in self.quantities["bends"]:
            angle = format_pipe_value(bend["angle_deg"])
            rows.append([
                str(len(rows) + 1), f'Отвод {angle}° {pipe["material"]} SDR {sdr} {diameter}',
                "", "", "", UNIT_PIECE, str(bend["quantity_pcs"]), "",
                "Материал и SDR приняты как у трубы",
            ])

        # характеристики из входа, неизвестные поля пустые.
        rows.append([
            str(len(rows) + 1), f'Труба {pipe["material"]} SDR {sdr} {diameter}×{wall}',
            pipe.get("standard") or "", "", "", UNIT_M, format_number(pipe["quantity_m"]), "",
            "Без запаса и вычета монтажных длин отводов",
        ])
        return rows

    def calculate_row_heights(self):
        """Возвращает высоты строк с учётом переносов и проверяет вместимость листа."""
        heights = []
        for row in self.rows:
            height = settings.SPEC_MIN_ROW_HEIGHT_MM
            for column, (value, width) in enumerate(zip(row, WIDTHS)):
                lines = TableCell(value, 0, 0, width, height, centered=column not in LEFT_ALIGNED_COLUMNS).lines
                height = max(height, len(lines) * settings.TABLE_CELL_LINE_STEP_MM)
            heights.append(height)
        remaining = settings.SPEC_BODY_HEIGHT_MM - sum(heights)
        if remaining < 0:
            raise ValueError("Таблица не помещается на один лист. Многостраничный выпуск пока не реализован.")
        if 0 < remaining < settings.SPEC_MIN_ROW_HEIGHT_MM and heights:
            heights[-1] += remaining
        return heights

    def table_body_svg(self, heights):
        """Возвращает SVG строк данных и горизонтальных линий таблицы."""
        row_top = settings.SPEC_BODY_TOP_MM
        right = settings.SPEC_TABLE_LEFT_MM + sum(WIDTHS)
        elements = [self.row_border_svg(row_top, right)]
        for index, (row, height) in enumerate(zip(self.rows, heights)):
            elements.append(f'<g id="spec-row-{index + 1}">')
            column_left = settings.SPEC_TABLE_LEFT_MM
            for column, (value, width) in enumerate(zip(row, WIDTHS)):
                elements.append(TableCell(value, column_left, row_top, width, height,
                                          centered=column not in LEFT_ALIGNED_COLUMNS).render())
                column_left += width
            elements.append('</g>')
            row_top += height
            elements.append(self.row_border_svg(row_top, right))
        while row_top + settings.SPEC_EMPTY_ROW_RESERVE_MM <= settings.SPEC_TABLE_BOTTOM_MM:
            row_top += settings.SPEC_MIN_ROW_HEIGHT_MM
            elements.append(self.row_border_svg(row_top, right))
        return "\n".join(elements)

    def row_border_svg(self, row_top, right):
        """Возвращает горизонтальную границу строки таблицы."""
        return (f'<path d="M {settings.SPEC_TABLE_LEFT_MM},{row_top} H {right:g}" '
                f'stroke="black" stroke-width="{settings.SPEC_GRID_LINE_WIDTH_MM}"/>')

    def table_header_svg(self):
        """Сетка, заголовки и текст строк используют одни ширины граф."""
        column_left = settings.SPEC_TABLE_LEFT_MM
        elements = []
        for header, width in zip(HEADERS, WIDTHS):
            header = HEADER_LINE_BREAKS.get(header, header)
            if column_left > settings.SPEC_TABLE_LEFT_MM:
                elements.append(f'<path d="M {column_left:g},{settings.SPEC_TABLE_TOP_MM} '
                                f'V {settings.SPEC_TABLE_BOTTOM_MM}" stroke="black" '
                                f'stroke-width="{settings.SPEC_GRID_LINE_WIDTH_MM}"/>')
            elements.append(TableCell(header, column_left, settings.SPEC_TABLE_TOP_MM, width,
                                      settings.SPEC_HEADER_HEIGHT_MM, centered=True).render())
            column_left += width
        return "\n".join(elements)

    def render(self):
        """Возвращает SVG-лист спецификации с таблицей и основной надписью."""
        heights = self.calculate_row_heights()
        table = render_template(TEMPLATE_PATH, {
            "font_family": settings.FONT_FAMILY,
            "font_size": settings.DEFAULT_FONT_SIZE_MM,
            "table_left": settings.SPEC_TABLE_LEFT_MM,
            "table_top": settings.SPEC_TABLE_TOP_MM,
            "table_height": settings.SPEC_TABLE_HEIGHT_MM,
            "table_width": f"{sum(WIDTHS):g}",
            "table_header": self.table_header_svg(),
            "table_body": self.table_body_svg(heights),
        })
        return self.sheet.render(table)

    def write_csv(self, path):
        """Записывает строки спецификации в CSV с теми же значениями, что на листе."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(HEADERS)
            writer.writerows(self.rows)
