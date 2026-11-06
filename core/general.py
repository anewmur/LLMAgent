from pathlib import Path
from string import Template

from core.calculations import calculate_route_geometry
from core.formatting import format_number
from core.sheet import Sheet
from core.tables import RegisterTable, TextBlock


TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "templates" / "general.svg"


class GeneralData:
    """Общие данные и ведомости из фактического состава выпуска."""

    def __init__(self, project, documents, config):
        self.project, self.documents, self.config = project, documents, config

    def drawing_register(self):
        rows = [[doc["number"], doc["title"], ""] for doc in self.documents.items
                if doc["suffix"] == "-НВ"]
        return RegisterTable(["Лист", "Наименование", "Примечание"], [15, 140, 30], rows)

    def set_register(self):
        code = self.project.object.project_code + "-НВ"
        return RegisterTable(["Обозначение", "Наименование", "Примечание"], [60, 95, 30],
                             [[code, "Наружные сети водоснабжения", ""]])

    def reference_register(self):
        rows = [["", "Ссылочные документы", ""]]
        rows.extend([[item["designation"], item["name"], ""] for item in self.config["references"]])
        spec = self.documents.get("spec")
        rows.extend([["", "Прилагаемые документы", ""], [spec["designation"], spec["title"], ""]])
        return RegisterTable(["Обозначение", "Наименование", "Примечание"], [60, 95, 30], rows)

    def paragraphs(self, paragraphs, x, y, width, bottom):
        elements = []
        for paragraph in paragraphs:
            block = TextBlock(paragraph, x, y, width)
            elements.append(block.render())
            y += len(block.lines) * 4.5 + 2
        if y > bottom:
            raise ValueError("Текст общих данных не помещается на листе: сократите реквизиты или добавьте лист.")
        return "\n".join(elements)

    def notes(self):
        p = self.project
        length = calculate_route_geometry(p.points)["length_m"]
        notes = [f"Объект: {p.object.name}. Основание: тестовое задание AI-агента.",
                 "Координаты заданы в условной местной системе, в метрах. "
                 "На плане положительное направление оси X принято вправо, оси Y — вверх листа. "
                 "Ориентация системы относительно сторон света исходными данными не задана.",
                 f"Сеть В1 — подземная напорная сеть водоснабжения. Длина трассы {format_number(length)} м.",
                 "Длина трубы принята по оси трассы в плане, без запаса и вычета монтажных длин отводов.",
                 "Профиль развёрнут по оси трассы. Сплошная толстая линия профиля обозначает трубу.",
                 "Учебный комплект. Для строительства не предназначен; нет подосновы и инженерных изысканий."]
        return notes

    def assumptions(self):
        return ["В1 назначено условно. Отметка земли принята проектной; натурная поверхность не задана.",
                "Материал и SDR отводов приняты как у трубы. Для учебного профиля принято отсутствие изоляции; основание не задано.",
                "Пропуски отметок не интерполируются. Полный перечень оговорок дан в отчёте о проверках."]

    def body(self):
        return Template(TEMPLATE_PATH.read_text(encoding="utf-8")).safe_substitute(
            drawings=self.drawing_register().render(), sets=self.set_register().render(),
            references=self.reference_register().render(),
            notes=self.paragraphs(self.notes(), 30, 152, 185, 233),
            assumptions=self.paragraphs(self.assumptions(), 230, 194, 180, 233),
        )

    def render(self):
        doc = self.documents.get("general")
        sheet = Sheet(doc["designation"], self.project.object.name, doc["title"], doc["number"], doc["total"])
        return sheet.render().replace('</svg>', self.body() + '\n</svg>')
