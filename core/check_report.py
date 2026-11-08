from core import drawing_settings as settings
from core.assumptions import (
    COORDINATE_ORIENTATION_NOTE,
    MISSING_BEND_STANDARD_NOTE,
    MISSING_DATA_NOTES,
    MISSING_PIPE_STANDARD_NOTE,
    SHARED_ASSUMPTIONS,
)
from core.formatting import format_pipe_value
from core.models import CheckResult, Status
from core.paths import TEMPLATES_DIR
from core.formatting import render_template


def check_status(checks: list[CheckResult]):
    """Возвращает статус: ошибка имеет приоритет перед предупреждением и успехом."""
    if any(check.status == Status.ERROR for check in checks):
        return Status.ERROR
    if any(check.status == Status.WARNING for check in checks):
        return Status.WARNING
    return Status.OK


class CheckReport:
    """Отчёт об автоматической сверке, просмотр и ограничения."""

    def __init__(self, project, config, checks, vertical_scale):
        """Сохраняет результаты проверок и вертикальный масштаб построенного профиля."""
        self.project, self.config = project, config
        self.checks, self.vertical_scale = checks, vertical_scale

    def missing_data(self):
        """Возвращает недостающие сведения с учётом наличия стандарта на трубу."""
        missing = list(MISSING_DATA_NOTES)
        if not self.project.pipe.standard:
            missing.append(MISSING_PIPE_STANDARD_NOTE)
        missing.append(MISSING_BEND_STANDARD_NOTE)
        return missing

    def write_template(self, path, name, values):
        """Записывает markdown-файл с подстановкой значений в шаблон."""
        text = render_template(TEMPLATES_DIR / name, values)
        path.write_text(text, encoding="utf-8")

    def assumptions(self):
        """Возвращает допущения и пояснение изображения трубы в масштабе профиля."""
        vertical_scale = self.vertical_scale
        diameter = format_pipe_value(self.project.pipe.outer_diameter_mm)
        on_paper = format_pipe_value(self.project.pipe.outer_diameter_mm / vertical_scale)
        threshold = settings.PROFILE_TWO_LINE_THRESHOLD_MM
        two_lines = self.project.pipe.outer_diameter_mm / vertical_scale >= threshold
        comparison, image = ("≥", "двумя линиями") if two_lines else ("<", "одной линией")
        pipe_note = (f"Труба ⌀{diameter} при 1:{vertical_scale:g} = {on_paper} мм {comparison} {threshold:g} мм, "
                     f"поэтому изображается {image} (п. 5.2.3 ГОСТ 21.704).")
        configured = [note.replace("{profile_two_line_threshold_mm}", f"{threshold:g}")
                      for note in self.config["assumptions"]]
        return list(SHARED_ASSUMPTIONS) + [COORDINATE_ORIENTATION_NOTE] + configured + [pipe_note]

    def checks_table(self):
        """Возвращает строки таблицы, различая ошибки и предупреждения."""
        rows = []
        for check in self.checks:
            result = "Пройдено"
            if check.status != Status.OK:
                result = "Предупреждение" if check.status == Status.WARNING else "Ошибка"
            detail = check.message.replace("|", "\\|").replace("\n", " ")
            rows.append(f'| {check.name} | {result} | {detail} |')
        return "\n".join(rows)

    @staticmethod
    def failure_message(checks):
        """Возвращает сообщение об отказе с названиями непройденных проверок."""
        names = ", ".join(check.name for check in checks if check.status != Status.OK)
        return "Проверки готовых документов не пройдены: " + names

    def write(self, folder):
        """Записывает отчёт и возвращает общий статус проверок."""
        status = check_status(self.checks)
        self.write_template(folder / "check_report.md", "check_report.md", {
            "object_name": self.project.object.name,
            "designation": self.project.object.project_code + settings.NETWORK_SUFFIX,
            "status": status,
            "checks": self.checks_table(),
            "missing": "\n".join("- " + line for line in self.missing_data()),
            "assumptions": "\n".join("- " + line for line in self.assumptions()),
            "limitations": "\n".join("- " + line for line in self.config["limitations"]),
        })
        return status
