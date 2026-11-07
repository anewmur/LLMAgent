import csv

from core.checks.base import BaseChecks
from core.formatting import format_number
from core.models import DocumentId, SpecificationColumn, UNIT_M, UNIT_PIECE


class SpecificationChecks(BaseChecks):
    """Количество трубы и отводов в спецификации."""

    def check_quantities(self):
        """Сверяет количество трубы с расчётом, а число отводов — с проектом."""
        with (self.folder / f"{DocumentId.SPECIFICATION}.csv").open(encoding="utf-8-sig", newline="") as stream:
            rows = list(csv.reader(stream, delimiter=";"))[1:]
        pipes = [row for row in rows if row[SpecificationColumn.UNIT] == UNIT_M]
        bends = [row for row in rows if row[SpecificationColumn.UNIT] == UNIT_PIECE]
        if len(pipes) != 1 or pipes[0][SpecificationColumn.QUANTITY] != format_number(self.geometry["length_m"]):
            self.add("quantities", False, "Количество трубы не равно расчётной длине трассы.")
            return
        if sum(int(row[SpecificationColumn.QUANTITY]) for row in bends) != len(self.project.bends):
            self.add("quantities", False, "Количество отводов не совпадает с исходными данными.")
            return
        self.add("quantities", True, "Количество трубы и отводов совпадает с расчётом.")

    def run(self):
        """Выполняет проверки группы в прежнем порядке."""
        self.run_checks(self.check_quantities)
