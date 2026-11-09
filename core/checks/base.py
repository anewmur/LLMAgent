from pathlib import Path
from xml.etree import ElementTree as ET

from pypdf.errors import PdfReadError

from core.calculations import calculate_point_levels, calculate_route_geometry
from core.models import CheckResult, Level, Status
from core import drawing_settings as settings
from core.pipe_drawing import pipe_size_text, leader_crosses_shelf_text


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

    def add(self, name, passed, detail, level=Level.ERROR, reference=""):
        """Добавляет результат одной проверки с её прежним идентификатором."""
        status = Status.OK if passed else Status(level)
        self.results.append(CheckResult(name, status, detail, reference))

    def check_pipe_label(self, document_id):
        """Сверяет обозначение и размер на полке с исходными данными трубы."""
        label = self.roots[document_id].find(".//s:g[@data-kind='pipe-label']", NS)
        if label is None and self.roots[document_id].find(".//s:g[@id='profile-pipe-label'][@data-placement='warning']", NS) is not None:
            self.add(f"{document_id}_pipe_label", False, "Полка не нанесена: нет свободного места.", level=Level.WARNING)
            return
        valid = label is not None
        if valid:
            network = label.find("s:text[@data-kind='pipe-network']", NS)
            size = label.find("s:text[@data-kind='pipe-size']", NS)
            valid = (network is not None and network.text == settings.NETWORK_CODE
                     and size is not None and size.text == pipe_size_text(self.project.pipe)
                     and label.find("s:path[@data-kind='pipe-leader']", NS) is not None)
        self.check_pipe_leader(document_id)
        self.add(f"{document_id}_pipe_label", valid, "Обозначение и размер трубы на полке соответствуют исходным данным."
                 if valid else "Полка трубы отсутствует или её обозначение и размер неверны.",
                 reference=settings.PIPE_LABEL_REFERENCE)

    def check_pipe_leader(self, document_id):
        """Добавляет предупреждение о пересечении выноски с текстами собственной полки."""
        label = self.roots[document_id].find(".//s:g[@data-kind='pipe-label']", NS)
        if label is not None:
            crosses = leader_crosses_shelf_text(label)
            self.add(f"{document_id}_leader_text", not crosses,
                     "Выноска трубы пересекает текст полки." if crosses else "Выноска не пересекает тексты полки.",
                     level=Level.WARNING)

    def run_checks(self, *checks) -> list[CheckResult]:
        """Выполняет проверки по порядку и записывает ошибки чтения под прежними id."""
        for check in checks:
            try:
                check()
            except (OSError, ValueError, AttributeError, IndexError, KeyError, ET.ParseError, PdfReadError) as error:
                self.add(check.__name__, False, str(error))

        return self.results
