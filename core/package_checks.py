from core.checks.base import CheckContext
from core.checks.general import GeneralChecks
from core.checks.pdf import PdfChecks
from core.checks.plan import PlanChecks
from core.checks.profile import ProfileChecks
from core.checks.sheet import SheetChecks
from core.checks.specification import SpecificationChecks


class PackageChecks:
    """Единая точка проверки готовых листов и PDF."""

    def __init__(self, project, documents, folder):
        """Сохраняет проект, состав комплекта и папку готовых документов."""
        self.project, self.documents, self.folder = project, documents, folder

    def run(self):
        """Запускает группы проверок и возвращает общий список результатов."""
        context = CheckContext(self.project, self.documents, self.folder)
        for check_class in (SheetChecks, PlanChecks, ProfileChecks,
                            SpecificationChecks, GeneralChecks, PdfChecks):
            checks = check_class(context)
            checks.run()
        return context.results
