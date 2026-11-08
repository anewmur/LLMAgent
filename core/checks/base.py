from pathlib import Path
from xml.etree import ElementTree as ET

from pypdf.errors import PdfReadError

from core.calculations import calculate_point_levels, calculate_route_geometry
from core.models import CheckResult, Level, Status


NS = {"s": "http://www.w3.org/2000/svg"}


class CheckContext:
    """Данные одного запуска проверок: расчёты, загруженные SVG и результаты."""

    def __init__(self, project, documents, folder):
        """Один раз рассчитывает геометрию, отметки и пикеты для всех групп."""
        self.project, self.documents, self.folder = project, documents, Path(folder)
        self.geometry = calculate_route_geometry(project.points)
        self.levels = calculate_point_levels(project.points, project.pipe.outer_diameter_mm)
        self.stations = [0] + [section["cumsum_dist_m"] for section in self.geometry["sections"]]
        self.results: list[CheckResult] = []
        self.roots = {}


class BaseChecks:
    """Общий доступ к данным запуска и сбор результатов проверок."""

    def __init__(self, context):
        """Подключает данные, SVG и результаты из единого контекста запуска."""
        self.project, self.documents, self.folder = context.project, context.documents, context.folder
        self.geometry, self.levels, self.stations = context.geometry, context.levels, context.stations
        self.results, self.roots = context.results, context.roots

    def add(self, name, passed, detail, level=Level.ERROR):
        """Добавляет результат одной проверки с её прежним идентификатором."""
        status = Status.OK if passed else Status(level)
        self.results.append(CheckResult(name, status, detail))

    def run_checks(self, *checks) -> list[CheckResult]:
        """Выполняет проверки по порядку и записывает ошибки чтения под прежними id."""
        for check in checks:
            try:
                check()
            except (OSError, ValueError, AttributeError, IndexError, KeyError, ET.ParseError, PdfReadError) as error:
                self.add(check.__name__, False, str(error))

        return self.results
