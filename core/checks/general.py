from core import drawing_settings as settings
from core.checks.base import BaseChecks, NS
from core.models import DocumentId


class GeneralChecks(BaseChecks):
    """Ведомости листов и прилагаемых документов общих данных."""

    def check_general(self):
        """Сверяет ведомости общих данных с фактическим составом выпуска."""
        root = self.roots[DocumentId.GENERAL]
        register = root.find(".//s:g[@id='drawing-register']", NS)
        text = "".join("".join(register.itertext()).split())
        for doc in self.documents.items:
            if doc["suffix"] == settings.NETWORK_SUFFIX and "".join(doc["title"].split()) not in text:
                self.add(DocumentId.GENERAL, False, "В ведомости отсутствует лист: " + doc["title"])
                return
        references = root.find(".//s:g[@id='reference-register']", NS)
        if self.documents.get(DocumentId.SPECIFICATION)["designation"] not in "".join(references.itertext()):
            self.add(DocumentId.GENERAL, False, "Спецификация не записана в прилагаемые документы.")
            return
        self.add(DocumentId.GENERAL, True, "Ведомости содержат фактические листы НВ и отдельную СО.")

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        self.run_checks(self.check_general)
