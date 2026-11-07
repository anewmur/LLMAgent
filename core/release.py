from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
import shutil

from pypdf import PdfReader, PdfWriter

from core.check_report import CheckReport
from core.documents import DocumentSet
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.formatting import format_change_value
from core.general import GeneralData
from core.models import DocumentId, Project, Status
from core.package_checks import PackageChecks
from core.paths import TEMPLATES_DIR
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.sheet import svg_to_pdf
from core.specification import SpecificationDrawing
from core.templates import render_template


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
        general = GeneralData(self.project, self.documents, self.config)
        (folder / f"{DocumentId.GENERAL}.svg").write_text(general.render(), encoding="utf-8")
        plan = PlanDrawing(self.project, self.documents.get(DocumentId.PLAN))
        self.save_drawing(folder, plan, DocumentId.PLAN)
        profile = ProfileDrawing(self.project, self.documents.get(DocumentId.PROFILE), self.font_size)
        self.save_drawing(folder, profile, DocumentId.PROFILE)
        specification = SpecificationDrawing(self.project, self.documents.get(DocumentId.SPECIFICATION))
        self.save_drawing(folder, specification, DocumentId.SPECIFICATION)
        specification.write_csv(folder / f"{DocumentId.SPECIFICATION}.csv")
        return profile.vertical_scale

    def merge_pdf(self, folder, name, stems):
        writer = PdfWriter()
        for stem in stems:
            writer.append(PdfReader(folder / "pdf" / f"{stem}.pdf"))
        with (folder / "pdf" / name).open("wb") as stream:
            writer.write(stream)

    def build_pdf(self, folder):
        (folder / "pdf").mkdir()
        stems = [doc["id"] for doc in self.documents.items]
        for stem in stems:
            svg_to_pdf(folder / f"{stem}.svg", folder / "pdf" / f"{stem}.pdf")
        self.merge_pdf(folder, "package.pdf", stems)

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
        (folder / "changes.md").write_text(render_template(TEMPLATES_DIR / "changes.md", {
            "entries": "\n".join(entries),
        }), encoding="utf-8")

    def publish(self, folder):
        shutil.rmtree(self.output_dir, ignore_errors=True)
        shutil.copytree(folder, self.output_dir)

    def create(self):
        try:
            with TemporaryDirectory(prefix="llmagent-release-") as temp:
                folder = Path(temp)
                vertical_scale = self.build_svg(folder)
                self.build_pdf(folder)
                checks = PackageChecks(self.project, self.documents, folder).run()
                status = CheckReport(self.project, self.config, checks, vertical_scale).write(folder)
                if status == Status.ERROR:
                    raise ValueError("Проверки готовых документов не пройдены: " + str(checks))
                self.write_changes(folder)
                self.publish(folder)
            return {"status": status, "folder": str(self.output_dir), "checks": checks,
                    "pdf": str(self.output_dir / "pdf" / "package.pdf"),
                    "report": str(self.output_dir / "check_report.md")}
        except (OSError, ValueError, TypeError, KeyError) as error:
            return {"status": Status.ERROR, "message": str(error)}


def create_package(project: Project, output_dir, config, changes=None, font_size=DEFAULT_FONT_SIZE_MM):
    return PackageRelease(project, output_dir, config, changes, font_size).create()
