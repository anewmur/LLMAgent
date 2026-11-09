from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from reportlab.pdfgen.canvas import Canvas
from reportlab.graphics import renderPDF

from core.check_report import CheckReport
from core.assumptions import load_assumptions, assumption_summary
from core.documents import DocumentSet
from config.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.formatting import format_change_value
from core.general import GeneralData
from core.models import DocumentId, Project, Status, ProblemCode
from core.package_checks import PackageChecks
from config.paths import TEMPLATES_DIR
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.sheet import svg_drawing
from config.settings import CHANGES_FILENAME
from core.specification import SpecificationDrawing
from core.formatting import render_template


def clear_output(output_dir):
    """Очищает каталог выпуска перед записью новых результатов."""
    folder = Path(output_dir)
    shutil.rmtree(folder, ignore_errors=True)
    folder.mkdir(parents=True, exist_ok=True)


class PackageRelease:
    """Комплект из текущего проекта; проверка предшествует публикации."""

    def __init__(self, project: Project, output_dir, config, changes=None, font_size=DEFAULT_FONT_SIZE_MM):
        self.project, self.output_dir = project, Path(output_dir)
        self.changes, self.font_size = changes or [], font_size
        self.config = config
        self.documents = DocumentSet(self.project, self.config)

    def save_drawing(self, folder, drawing, document_id):
        doc = self.documents.get(document_id)
        drawing.sheet.number, drawing.sheet.total = doc["number"], doc["total"]
        (folder / f"{document_id}.svg").write_text(drawing.render(), encoding="utf-8")

    def build_svg(self, folder):
        plan = PlanDrawing(self.project, self.documents.get(DocumentId.PLAN))
        profile = ProfileDrawing(self.project, self.documents.get(DocumentId.PROFILE), self.config, self.font_size)
        self.assumptions = load_assumptions(self.config, self.project, profile.vertical_scale, plan.scale)
        general = GeneralData(self.project, self.documents, self.config, self.assumptions)
        (folder / f"{DocumentId.GENERAL}.svg").write_text(general.render(), encoding="utf-8")
        self.save_drawing(folder, plan, DocumentId.PLAN)
        self.save_drawing(folder, profile, DocumentId.PROFILE)
        specification = SpecificationDrawing(self.project, self.documents.get(DocumentId.SPECIFICATION))
        self.save_drawing(folder, specification, DocumentId.SPECIFICATION)
        specification.write_csv(folder / f"{DocumentId.SPECIFICATION}.csv")

    def build_pdf(self, folder):
        """Записывает все листы непосредственно в один PDF, без отдельных файлов страниц."""
        (folder / "pdf").mkdir()
        canvas = Canvas(str(folder / "pdf/package.pdf"))
        for document in self.documents.items:
            drawing = svg_drawing(folder / f'{document["id"]}.svg')
            canvas.setPageSize((drawing.width, drawing.height))
            renderPDF.draw(drawing, canvas, 0, 0)
            canvas.showPage()
        canvas.save()

    def write_changes(self, folder):
        if not self.changes:
            return
        entries = []
        for number, change_set in enumerate(self.changes, 1):
            change = asdict(change_set)
            values = [f'- {value["name"]}: **{format_change_value(value["before"])} → '
                      f'{format_change_value(value["after"])}'
                      f'{" " + value["unit"] if value["unit"] else ""}**.' for value in change["values"]]
            entries.append(render_template(TEMPLATES_DIR / "change_entry.md", {
                "number": number,
                "title": change["title"],
                "values": "\n".join(values),
                "sheets": ", ".join(change["sheets"]),
            }))
        (folder / CHANGES_FILENAME).write_text(render_template(TEMPLATES_DIR / CHANGES_FILENAME, {
            "entries": "\n".join(entries),
        }), encoding="utf-8")

    def publish(self, folder):
        shutil.rmtree(self.output_dir, ignore_errors=True)
        shutil.copytree(folder, self.output_dir)

    def create(self):
        try:
            with TemporaryDirectory(prefix="llmagent-release-") as temp:
                folder = Path(temp)
                self.build_svg(folder)
                self.build_pdf(folder)
                checks = PackageChecks(self.project, self.documents, folder).run()
                report = CheckReport(self.project, self.config, checks, self.assumptions)
                status = report.write(folder)
                if status == Status.ERROR:
                    problems = report.problems()
                    return {"status": status, "released": False, "message": CheckReport.failure_message(checks),
                            "checks": checks, "problems": problems}
                self.write_changes(folder)
                self.publish(folder)
            return {"status": status, "released": True, "folder": str(self.output_dir), "checks": checks, "problems": report.problems(),
                    **assumption_summary(self.assumptions),
                    "pdf": str(self.output_dir / "pdf" / "package.pdf"),
                    "report": str(self.output_dir / "check_report.md")}
        except (OSError, ValueError, TypeError, KeyError) as error:
            problems = [{"code": ProblemCode.RELEASE_FAILED, "level": Status.ERROR, "where": "", "message": str(error)}]
            return {"status": Status.ERROR, "released": False, "message": str(error),
                    "problems": problems}


def create_package(project: Project, output_dir, config, changes=None, font_size=DEFAULT_FONT_SIZE_MM):
    return PackageRelease(project, output_dir, config, changes, font_size).create()
