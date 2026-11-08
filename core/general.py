from core import drawing_settings as settings
from core.assumptions import (
    BEND_MATERIAL_ASSUMPTION,
    COORDINATE_SYSTEM_NOTE,
    MISSING_LEVELS_ASSUMPTION,
    NETWORK_AND_GROUND_ASSUMPTION,
    PROFILE_INSULATION_ASSUMPTION,
)
from core.calculations import calculate_route_geometry
from core.formatting import format_number, format_pipe_value
from core.models import DocumentId
from core.paths import TEMPLATES_DIR
from core.sheet import Sheet
from core.tables import RegisterTable, TextBlock
from core.formatting import render_template


TEMPLATE_PATH = TEMPLATES_DIR / "general.svg"
REGISTER_HEADERS = ("Обозначение", "Наименование", "Примечание")
DRAWING_REGISTER_HEADERS = ("Лист", "Наименование", "Примечание")
NETWORK_NAME = "Наружные сети водоснабжения"
GENERAL_NOTES = (
    "Основанием для разработки является задание на проектирование.",
    COORDINATE_SYSTEM_NOTE,
    "Проектируемая сеть {network_code} — подземный напорный водопровод из труб {pipe}. Длина трассы — {length} м.",
    "Длина трубы в спецификации принята по оси трассы без запаса.",
    "В исходных данных заданы отметки оси трубопровода; на профиле показаны отметки низа трубы "
    "(ось минус половина наружного диаметра). Труба показана сплошной толстой линией.",
    "Принятые допущения и ограничения приведены в отчёте о проверках.",
)


class GeneralData:
    """Общие данные и ведомости из фактического состава выпуска."""

    def __init__(self, project, documents, config):
        """Сохраняет проект, состав документов и настройки общих данных."""
        self.project, self.documents, self.config = project, documents, config

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
        """Возвращает шесть общих указаний с трубой и длиной из проекта."""
        pipe = self.project.pipe
        pipe_description = (f"{pipe.material} SDR {format_pipe_value(pipe.sdr)} "
                            f"{format_pipe_value(pipe.outer_diameter_mm)}×{format_pipe_value(pipe.wall_mm)}")
        length = calculate_route_geometry(self.project.points)["length_m"]
        return [note.format(network_code=settings.NETWORK_CODE, pipe=pipe_description, length=format_number(length)) for note in GENERAL_NOTES]

    def assumptions(self):
        """Возвращает краткие допущения из общих с отчётом формулировок."""
        return [NETWORK_AND_GROUND_ASSUMPTION,
                f"{BEND_MATERIAL_ASSUMPTION} {PROFILE_INSULATION_ASSUMPTION}",
                f"{MISSING_LEVELS_ASSUMPTION} Полный перечень оговорок дан в отчёте о проверках."]

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
            "assumptions": self.paragraphs(self.assumptions(), settings.GENERAL_ASSUMPTIONS_LEFT_MM,
                                        settings.GENERAL_ASSUMPTIONS_TOP_MM, settings.GENERAL_ASSUMPTIONS_WIDTH_MM,
                                        settings.GENERAL_TEXT_BOTTOM_MM),
        })

    def render(self):
        """Возвращает лист общих данных с реквизитами из состава комплекта."""
        doc = self.documents.get(DocumentId.GENERAL)
        sheet = Sheet(doc["designation"], self.project.object.name, doc["title"], total=doc["total"])
        sheet.number = doc["number"]
        return sheet.render(self.body())
