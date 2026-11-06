from pathlib import Path
from string import Template

ROOT = Path(__file__).resolve().parent.parent


class CheckReport:
    """Отчёт различает автоматическую сверку, просмотр и ограничения."""

    def __init__(self, project, config, checks, problems):
        self.project, self.config = project, config
        self.checks, self.problems = checks, problems

    def missing_data(self):
        missing = ["Не заданы организация, исполнители, подписи и даты в основной надписи.",
                   "Не заданы поставщик, код продукции и масса единицы в спецификации.",
                   "Не заданы натурная поверхность, основание, геология и УГВ."]
        if not self.project.pipe.standard:
            missing.append("Не задан стандарт или ТУ на трубу; графа документа оставлена пустой.")
        missing.append("Материал и SDR отводов приняты как у трубы; документ на отводы не задан.")
        return missing

    def write_template(self, path, name, values):
        text = Template((ROOT / "templates" / name).read_text(encoding="utf-8")).safe_substitute(values)
        path.write_text(text, encoding="utf-8")

    def assumptions(self):
        diameter = f"{self.project.pipe.outer_diameter_mm:g}".replace(".", ",")
        on_paper = f"{self.project.pipe.outer_diameter_mm / 100:g}".replace(".", ",")
        two_lines = self.project.pipe.outer_diameter_mm / 100 >= 2
        comparison, image = ("≥", "двумя линиями") if two_lines else ("<", "одной линией")
        pipe_note = (f"Труба ⌀{diameter} при 1:100 = {on_paper} мм {comparison} 2 мм, "
                     f"поэтому изображается {image} (п. 5.2.3 ГОСТ 21.704).")
        return self.config["assumptions"] + [pipe_note]

    def write(self, folder):
        status = "ok" if all(row["passed"] for row in self.checks) else "error"
        self.write_template(folder / "check_report.md", "check_report.md", {
            "object_name": self.project.object.name, "designation": self.project.object.project_code + "-НВ",
            "status": status,
            "checks": "\n".join(f'| {r["id"]} | {"Пройдено" if r["passed"] else "Ошибка"} | {r["detail"]} |' for r in self.checks),
            "problems": "\n".join(f'- {p["where"]}: {p["message"]}' for p in self.problems) or "Не обнаружены.",
            "missing": "\n".join("- " + line for line in self.missing_data()),
            "assumptions": "\n".join("- " + line for line in self.assumptions()),
            "limitations": "\n".join("- " + line for line in self.config["limitations"]),
        })
        return status
