from core import drawing_settings as settings
from core.models import CheckResult, Status
from core.settings import RELEASE_REFUSED_STATUS
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

    def __init__(self, project, config, checks, assumptions):
        """Сохраняет результаты проверок и подготовленный список допущений."""
        self.project, self.config = project, config
        self.checks, self.items = checks, assumptions

    @staticmethod
    def write_rejection(folder, problems):
        """Записывает отказ с теми же кодами, точками и сообщениями, что получает агент."""
        rows = []
        for problem in problems:
            if problem["level"] != Status.ERROR:
                continue
            values = (problem["code"], problem.get("where") or "—", problem["message"])
            cells = [str(value).replace("|", "\\|").replace("\n", " ") for value in values]
            rows.append("| " + " | ".join(cells) + " |")
        path = folder / "check_report.md"
        CheckReport.write_template(path, "rejected_report.md", {
            "status": RELEASE_REFUSED_STATUS, "errors": "\n".join(rows),
        })
        return str(path)

    def problems(self):
        """Возвращает ошибки и предупреждения проверок для ответа инструмента и отказа."""
        return [{"code": check.name, "level": check.status, "where": "", "message": check.message}
                for check in self.checks if check.status != Status.OK]

    def missing_data(self):
        """Возвращает недостающие сведения с учётом наличия стандарта на трубу."""
        missing = list(self.config["missing_data"]["common"])
        if not self.project.pipe.standard:
            missing.append(self.config["missing_data"]["pipe_standard"])
        missing.append(self.config["missing_data"]["bend_standard"])
        return missing

    @staticmethod
    def write_template(path, name, values):
        """Записывает markdown-файл с подстановкой значений в шаблон."""
        text = render_template(TEMPLATES_DIR / name, values)
        path.write_text(text, encoding="utf-8")

    def assumptions(self):
        """Возвращает полные формулировки из единого списка допущений."""
        return [item.full for item in self.items]

    def checks_table(self):
        """Возвращает строки таблицы, различая ошибки и предупреждения."""
        rows = []
        for check in self.checks:
            result = "Пройдено"
            if check.status != Status.OK:
                result = "Предупреждение" if check.status == Status.WARNING else "Ошибка"
            detail = check.message.replace("|", "\\|").replace("\n", " ")
            if check.reference:
                detail += f" ({check.reference})"
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
