from pypdf import PdfReader

from core import drawing_settings as settings
from core.checks.base import BaseChecks
from core.formatting import format_number, format_station
from core.models import DocumentId


class PdfChecks(BaseChecks):
    """Открытие PDF, обозначения, значения и комплектность объединённого файла."""

    def pdf_values(self, document_id):
        """Возвращает расчётные значения, которые должны присутствовать в PDF листа."""
        if document_id == DocumentId.SPECIFICATION:
            return [format_number(self.geometry["length_m"])]
        if document_id == DocumentId.GENERAL:
            return [doc["title"] for doc in self.documents.items if doc["suffix"] == settings.NETWORK_SUFFIX]
        values = [format_station(station) for station in self.stations]
        values += [format_number(section["length_m"]) for section in self.geometry["sections"]]
        if document_id == DocumentId.PROFILE:
            values += [format_number(point["bottom_m"]) for point in self.levels if point["bottom_m"] is not None]
            values += [format_number(section["slope_per_mille"]) for section in self.geometry["sections"] if section["slope_per_mille"] is not None]
        if document_id == DocumentId.PLAN:
            values += [f"X={format_number(point.x)}, Y={format_number(point.y)}" for point in self.project.points]
        return values

    def check_pdf_page(self, doc):
        """Проверяет открытие PDF листа, его обозначение и расчётные значения."""
        name = "pdf_" + doc["id"]
        stem = doc["id"]
        reader = PdfReader(self.folder / "pdf" / f"{stem}.pdf")
        text = "\n".join(page.extract_text() for page in reader.pages)
        if doc["designation"] not in text:
            self.add(name, False, "В PDF отсутствует обозначение.")
            return
        compact = "".join(text.split())
        for value in self.pdf_values(doc["id"]):
            if "".join(value.split()) not in compact:
                self.add(name, False, "В PDF отсутствует значение: " + value)
                return
        self.add(name, True, "PDF открывается, обозначение и значения верны.")

    def check_pdf(self):
        """Проверяет PDF листов и число страниц объединённого файла."""
        for doc in self.documents.items:
            self.check_pdf_page(doc)
        if len(PdfReader(self.folder / "pdf" / "package.pdf").pages) != len(self.documents.items):
            self.add("merged_pdf", False, "Неверное число страниц: package.pdf")
            return
        self.add("merged_pdf", True, "Количество страниц package.pdf совпадает с составом выпуска.")

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        self.run_checks(self.check_pdf)
