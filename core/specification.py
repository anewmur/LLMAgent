import csv
from pathlib import Path
from string import Template
from textwrap import wrap
from xml.sax.saxutils import escape

from core.calculations import INPUT_PATH, calculate_material_quantities, load_project
from core.formatting import format_number
from core.sheet import Sheet


# REQ-048, REQ-052: форма 1 ГОСТ 21.110-2013, ширины граф в миллиметрах.
HEADERS = [
    "Поз.", "Наименование и техническая характеристика",
    "Тип, марка, обозначение документа, опросного листа",
    "Код продукции", "Поставщик", "Ед. измерения", "Количество",
    "Масса 1 ед., кг", "Примечание",
]
WIDTHS = [20, 130, 60, 35, 45, 20, 20, 25, 40]
OUTPUT_DIR = INPUT_PATH.parent.parent / "output"
TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "specification.svg"


class Specification:
    """Подготовка и сохранение спецификации по постоянному SVG-макету."""

    def __init__(self, input_file=INPUT_PATH,
                 title="Спецификация оборудования, изделий и материалов", number="", total=1):
        self.input_file = Path(input_file)
        self.title = title
        self.number = number
        self.total = total
        self.project = None
        self.quantities = None
        self.rows = []

    def create(self, output_dir=OUTPUT_DIR):
        self.quantities = calculate_material_quantities(self.input_file)
        if self.quantities["status"] == "error":
            return self.quantities
        self.project, _ = load_project(self.input_file)
        self.rows = self.build_rows()
        try:
            svg = self.render_svg()
        except ValueError as error:
            return {"status": "error", "message": str(error)}
        return {
            "status": "ok",
            "files": self.save_files(output_dir, svg),
            "problems": self.quantities["problems"],
        }

    def build_rows(self):
        """Один список строк для CSV и SVG; количества уже рассчитаны."""
        pipe = self.quantities["pipe"]
        diameter = f'{pipe["outer_diameter_mm"]:g}'.replace(".", ",")
        wall = f'{pipe["wall_mm"]:g}'.replace(".", ",")
        sdr = f'{pipe["sdr"]:g}'.replace(".", ",")
        rows = []

        # REQ-044, REQ-045, REQ-046: изделия перед трубой; отводы в штуках.
        # ГОСТ 21.704-2011, п. 7.4: исключение не применяется — отводы заданы в ТЗ.
        for bend in self.quantities["bends"]:
            angle = f'{bend["angle_deg"]:g}'.replace(".", ",")
            rows.append([
                str(len(rows) + 1), f'Отвод {angle}° {pipe["material"]} SDR {sdr} {diameter}',
                "", "", "", "шт.", str(bend["quantity_pcs"]), "",
                "Материал и SDR приняты как у трубы",
            ])

        # REQ-053, REQ-054, REQ-055: характеристики из входа, неизвестные поля пустые.
        rows.append([
            str(len(rows) + 1), f'Труба {pipe["material"]} SDR {sdr} {diameter}×{wall}',
            pipe.get("standard") or "", "", "", "м", format_number(pipe["quantity_m"]), "",
            "Без запаса и вычета монтажных длин отводов",
        ])
        return rows

    def cell_lines(self, value, width, centered):
        """Одинаковые переносы для вывода текста и определения высоты строки."""
        return wrap(
            str(value), width=max(4, int((width - 4) / 1.7)),
            break_long_words=not centered,
        )

    def cell_text(self, value, x, y, width, height, centered):
        """Перенос текста внутри ячейки таблицы."""
        lines = self.cell_lines(value, width, centered)
        elements = []
        for i, line in enumerate(lines):
            text_x = x + width / 2 if centered else x + 2
            text_y = y + height / 2 + 1.2 + (i - (len(lines) - 1) / 2) * 4
            anchor = "middle" if centered else "start"
            elements.append(
                f'<text x="{text_x:g}" y="{text_y:g}" text-anchor="{anchor}">{escape(line)}</text>'
            )
        return "\n".join(elements)

    def calculate_row_heights(self):
        heights = []
        for row in self.rows:
            height = 8
            for column, (value, width) in enumerate(zip(row, WIDTHS)):
                lines = self.cell_lines(value, width, centered=column not in (1, 8))
                height = max(height, len(lines) * 4)
            heights.append(height)
        remaining = 160 - sum(heights)
        if remaining < 0:
            raise ValueError("Таблица не помещается на один лист. Многостраничный выпуск пока не реализован.")
        if 0 < remaining < 8 and heights:
            heights[-1] += remaining
        return heights

    def table_body_svg(self, heights):
        y = 62
        right = 20 + sum(WIDTHS)
        elements = [f'<path d="M 20,{y} H {right:g}" stroke="black" stroke-width="0.3"/>']
        for i, (row, height) in enumerate(zip(self.rows, heights)):
            elements.append(f'<g id="spec-row-{i + 1}">')
            x = 20
            for column, (value, width) in enumerate(zip(row, WIDTHS)):
                elements.append(self.cell_text(value, x, y, width, height, centered=column not in (1, 8)))
                x += width
            elements.append('</g>')
            y += height
            elements.append(f'<path d="M 20,{y} H {right:g}" stroke="black" stroke-width="0.3"/>')
        while y + 16 <= 222:
            y += 8
            elements.append(f'<path d="M 20,{y} H {right:g}" stroke="black" stroke-width="0.3"/>')
        return "\n".join(elements)

    def table_header_svg(self):
        """Сетка, заголовки и текст строк используют одни ширины граф."""
        x = 20
        elements = []
        for header, width in zip(HEADERS, WIDTHS):
            if x > 20:
                elements.append(f'<path d="M {x:g},30 V 222" stroke="black" stroke-width="0.3"/>')
            elements.append(self.cell_text(header, x, 30, width, 32, centered=True))
            x += width
        return "\n".join(elements)

    def render_svg(self):
        heights = self.calculate_row_heights()
        template = Template(TEMPLATE_PATH.read_text(encoding="utf-8"))
        table = template.substitute(
            table_width=f"{sum(WIDTHS):g}",
            table_header=self.table_header_svg(),
            table_body=self.table_body_svg(heights),
        )
        sheet = Sheet(
            self.project.object.project_code + "-НВ.СО", self.project.object.name,
            self.title, self.number, self.total,
        ).render()
        return sheet.replace("</svg>", table + "\n</svg>")

    def save_files(self, output_dir, svg):
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        csv_path = output_dir / "specification.csv"
        svg_path = output_dir / "specification.svg"
        with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(HEADERS)
            writer.writerows(self.rows)
        svg_path.write_text(svg, encoding="utf-8")
        return {"csv": str(csv_path), "svg": str(svg_path)}


def create_specification(input_file=INPUT_PATH, output_dir=OUTPUT_DIR):
    return Specification(input_file).create(output_dir)


if __name__ == "__main__":
    print(create_specification())
