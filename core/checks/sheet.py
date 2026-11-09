from xml.etree import ElementTree as ET

from config import drawing_settings as settings

from core.checks.base import BaseChecks, NS


class SheetChecks(BaseChecks):
    """Обозначения, названия и нумерация листов."""

    def check_sheets(self):
        """Загружает SVG и сверяет реквизиты каждого листа."""
        for doc in self.documents.items:
            stem = doc["id"]
            root = ET.parse(self.folder / f"{stem}.svg").getroot()
            self.roots[doc["id"]] = root
            self.check_sheet_text(doc, root)

    def check_sheet_text(self, doc, root):
        """Сверяет реквизиты и нумерацию листа с составом выпуска."""
        name = "stamp_" + doc["id"]
        text = "".join("".join(root.itertext()).split())
        for value in [doc["designation"], doc["title"]]:
            if "".join(value.split()) not in text:
                self.add(name, False, "В листе отсутствует реквизит: " + value)
                return
        for cell_x, expected in [(settings.SHEET_NUMBER_X_MM, doc["number"]), (settings.SHEET_TOTAL_X_MM, doc["total"])]:
            cell = root.find(f".//s:text[@x='{cell_x:g}'][@y='{settings.SHEET_NUMBER_Y_MM:g}']", NS)
            if (cell.text or "") != str(expected):
                self.add(name, False, "Номер листа или число листов не совпадает с составом выпуска.")
                return
        self.add(name, True, "Реквизиты и нумерация совпадают с составом выпуска.")

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        return self.run_checks(self.check_sheets)
