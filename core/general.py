from xml.sax.saxutils import quoteattr

from core import drawing_settings as settings
from core.calculations import calculate_route_geometry
from core.formatting import format_number, format_pipe_value, render_template
from core.models import DocumentId
from core.paths import TEMPLATES_DIR
from core.sheet import Sheet
from core.tables import RegisterTable, TextBlock


TEMPLATE_PATH = TEMPLATES_DIR / "general.svg"
ASSUMPTION_TEMPLATE_PATH = TEMPLATES_DIR / "assumption.svg"
REGISTER_HEADERS = ("Обозначение", "Наименование", "Примечание")
DRAWING_REGISTER_HEADERS = ("Лист", "Наименование", "Примечание")
NETWORK_NAME = "Наружные сети водоснабжения"


class GeneralData:
    """Общие данные и ведомости из фактического состава выпуска."""

    def __init__(self, project, documents, config, assumptions):
        """Сохраняет проект, состав документов и настройки общих данных."""
        self.project, self.documents, self.config = project, documents, config
        self.items = assumptions

    def drawing_register(self):
        """Возвращает ведомость листов основного комплекта."""
        rows = [[doc["number"], doc["title"], ""] for doc in self.documents.items
                if doc["suffix"] == settings.NETWORK_SUFFIX]
        return RegisterTable(DRAWING_REGISTER_HEADERS, settings.GENERAL_DRAWING_REGISTER_WIDTHS_MM, rows)

    def set_register(self):
        """Возвращает ведомость основных комплектов рабочих чертежей."""
        code = self.project.object.project_code + settings.NETWORK_SUFFIX
        return RegisterTable(REGISTER_HEADERS, settings.GENERAL_REGISTER_WIDTHS_MM,
                             [[code, NETWORK_NAME, ""]])

    def reference_register(self):
        """Возвращает ведомость ссылочных и прилагаемых документов."""
        rows = [["", "Ссылочные документы", ""]]
        rows.extend([[item["designation"], item["name"], ""] for item in self.config["references"]])
        spec = self.documents.get(DocumentId.SPECIFICATION)
        rows.extend([["", "Прилагаемые документы", ""], [spec["designation"], spec["title"], ""]])
        return RegisterTable(REGISTER_HEADERS, settings.GENERAL_REGISTER_WIDTHS_MM, rows)

    def paragraphs(self, paragraphs, left, top, width, bottom):
        """Возвращает SVG абзацев и проверяет нижнюю границу текстового поля."""
        elements = []
        for paragraph in paragraphs:
            block = TextBlock(paragraph, left, top, width)
            elements.append(block.render())
            top += len(block.lines) * settings.TEXT_LINE_STEP_MM + settings.GENERAL_PARAGRAPH_GAP_MM
        if top > bottom:
            raise ValueError("Текст общих данных не помещается на листе: сократите реквизиты или добавьте лист.")
        return "\n".join(elements)

    def notes(self):
        """Возвращает общие указания из конфигурации с трубой и длиной из проекта."""
        pipe = self.project.pipe
        pipe_description = (f"{pipe.material} SDR {format_pipe_value(pipe.sdr)} "
                            f"{format_pipe_value(pipe.outer_diameter_mm)}×{format_pipe_value(pipe.wall_mm)}")
        length = calculate_route_geometry(self.project.points)["length_m"]
        values = {item.id: item.full for item in self.items}
        values.update(network_code=settings.NETWORK_CODE,
                      pipe=pipe_description, length=format_number(length))
        return [note.format(**values) for note in self.config["general_notes"]]

    def draw_assumptions(self):
        """Выводит ключевые допущения справа и ссылку на полный перечень."""
        elements = []
        top = settings.GENERAL_ASSUMPTIONS_TOP_MM
        for item in self.items:
            if not item.key:
                continue
            block = TextBlock(item.short, settings.GENERAL_ASSUMPTIONS_LEFT_MM, top,
                              settings.GENERAL_ASSUMPTIONS_WIDTH_MM)
            elements.append(render_template(ASSUMPTION_TEMPLATE_PATH, {
                "id": quoteattr(item.id), "body": block.render(),
            }))
            top += len(block.lines) * settings.TEXT_LINE_STEP_MM + settings.GENERAL_PARAGRAPH_GAP_MM
        footer = TextBlock(self.config["assumptions_footer"], settings.GENERAL_ASSUMPTIONS_LEFT_MM,
                           top, settings.GENERAL_ASSUMPTIONS_WIDTH_MM)
        if top + (len(footer.lines) - 1) * settings.TEXT_LINE_STEP_MM > settings.GENERAL_TEXT_BOTTOM_MM:
            raise ValueError("Допущения не помещаются на листе общих данных.")
        elements.append(footer.render())
        return "\n".join(elements)

    def body(self):
        """Возвращает SVG ведомостей, указаний и допущений по шаблону."""
        return render_template(TEMPLATE_PATH, {
            "font_family": settings.FONT_FAMILY,
            "font_size": settings.DEFAULT_FONT_SIZE_MM,
            "drawings": self.drawing_register().render(),
            "sets": self.set_register().render(),
            "references": self.reference_register().render(),
            "notes": self.paragraphs(self.notes(), settings.GENERAL_NOTES_LEFT_MM,
                                  settings.GENERAL_NOTES_TOP_MM, settings.GENERAL_NOTES_WIDTH_MM,
                                  settings.GENERAL_TEXT_BOTTOM_MM),
            "assumptions": self.draw_assumptions(),
        })

    def render(self):
        """Возвращает лист общих данных с реквизитами из состава комплекта."""
        doc = self.documents.get(DocumentId.GENERAL)
        sheet = Sheet(doc["designation"], self.project.object.name, doc["title"], total=doc["total"])
        sheet.number = doc["number"]
        return sheet.render(self.body())
