import argparse
import json
import shutil
from pathlib import Path
from string import Template
from tempfile import TemporaryDirectory

import yaml
from pypdf import PdfReader, PdfWriter

from core.calculations import INPUT_PATH, load_project
from core.formatting import format_number
from core.check_report import CheckReport
from core.documents import DocumentSet
from core.general import GeneralData
from core.package_checks import PackageChecks
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.sheet import svg_to_pdf
from core.specification import create_specification


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "requirements.yaml"
OUTPUT_DIR = ROOT / "output"


class PackageRelease:
    """Комплект из текущего проекта; проверка предшествует публикации."""

    def __init__(self, project=INPUT_PATH, output_dir=OUTPUT_DIR, changes=None, font_size=3.5):
        self.source, self.output_dir = project, Path(output_dir)
        self.changes, self.font_size = changes or [], font_size
        self.config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
        self.project, self.problems = None, []

    def load(self):
        self.project, self.problems = load_project(self.source)
        if self.project is None or any(p["level"] == "error" for p in self.problems):
            raise ValueError("Исходные данные не прошли проверку.")
        self.documents = DocumentSet(self.project, self.config)

    def save_drawing(self, folder, drawing, document_id):
        doc = self.documents.get(document_id)
        drawing.sheet.number, drawing.sheet.total = doc["number"], doc["total"]
        drawing.sheet.title = doc["title"]
        (folder / f"{document_id}.svg").write_text(drawing.render(), encoding="utf-8")

    def build_svg(self, folder):
        general = GeneralData(self.project, self.documents, self.config)
        (folder / "general.svg").write_text(general.render(), encoding="utf-8")
        self.save_drawing(folder, PlanDrawing(self.project), "plan")
        self.save_drawing(folder, ProfileDrawing(self.project, self.font_size), "profile")
        doc = self.documents.get("spec")
        result = create_specification(self.project, folder, doc["title"], doc["number"], doc["total"])
        if result["status"] != "ok":
            raise ValueError(result.get("message", "Не удалось сформировать спецификацию."))

    def merge_pdf(self, folder, name, stems):
        writer = PdfWriter()
        for stem in stems:
            writer.append(PdfReader(folder / "pdf" / f"{stem}.pdf"))
        with (folder / "pdf" / name).open("wb") as stream:
            writer.write(stream)

    def build_pdf(self, folder):
        (folder / "pdf").mkdir()
        stems = ["specification" if doc["id"] == "spec" else doc["id"] for doc in self.documents.items]
        for stem in stems:
            svg_to_pdf(folder / f"{stem}.svg", folder / "pdf" / f"{stem}.pdf")
        self.merge_pdf(folder, "package.pdf", stems)

    def write_changes(self, folder):
        if not self.changes:
            return
        template = Template((ROOT / "templates" / "change_entry.md").read_text(encoding="utf-8"))
        entries = []
        for number, change in enumerate(self.changes, 1):
            values = [f'- {v["name"]}: **{format_number(v["before"])} → '
                      f'{format_number(v["after"])} {v["unit"]}**.' for v in change["values"]]
            entries.append(template.safe_substitute(number=number, title=change["title"],
                                                    values="\n".join(values), sheets=", ".join(change["sheets"])))
        text = Template((ROOT / "templates" / "changes.md").read_text(encoding="utf-8"))
        (folder / "changes.md").write_text(text.safe_substitute(entries="\n".join(entries)), encoding="utf-8")

    def publish(self, folder):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        for target in sorted(self.output_dir.rglob("*"), reverse=True):
            source = folder / target.relative_to(self.output_dir)
            if target.is_symlink():
                target.unlink()
            elif target.is_file() and not source.is_file():
                target.unlink()
            elif target.is_dir() and not any(target.iterdir()):
                target.rmdir()
        for source in folder.rglob('*'):
            if source.is_file():
                target = self.output_dir / source.relative_to(folder)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    def create(self):
        try:
            with TemporaryDirectory(prefix="llmagent-release-") as temp:
                folder = Path(temp)
                self.load()
                self.build_svg(folder)
                self.build_pdf(folder)
                checks = PackageChecks(self.project, self.documents, folder).run()
                status = CheckReport(self.project, self.config, checks, self.problems).write(folder)
                if status == "error":
                    raise ValueError("Проверки готовых документов не пройдены: " + str(checks))
                self.write_changes(folder)
                self.publish(folder)
            return {"status": status, "folder": str(self.output_dir), "checks": checks,
                    "problems": self.problems, "pdf": str(self.output_dir / "pdf" / "package.pdf"),
                    "report": str(self.output_dir / "check_report.md")}
        except (OSError, ValueError, TypeError, KeyError) as error:
            return {"status": "error", "message": str(error), "problems": self.problems}


def create_package(project=INPUT_PATH, output_dir=OUTPUT_DIR, changes=None, font_size=3.5):
    return PackageRelease(project, output_dir, changes, font_size).create()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Выпуск учебного комплекта без LLM")
    parser.add_argument("--input", type=Path, default=INPUT_PATH)
    args = parser.parse_args()
    result = create_package(args.input)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(1 if result["status"] == "error" else 0)
