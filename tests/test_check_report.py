from core.assumptions import MISSING_PIPE_STANDARD_NOTE
from core.check_report import CheckReport, check_status
from core.models import CheckResult, Project, Status


def test_check_status_prioritizes_failed_errors():
    passed = CheckResult("passed", Status.OK, "Пройдено")
    warning = CheckResult("warning", Status.WARNING, "Предупреждение")
    error = CheckResult("error", Status.ERROR, "Ошибка")
    assert check_status([]) == "ok"
    assert check_status([passed]) == "ok"
    assert check_status([passed, warning]) == "warning"
    assert check_status([warning, error]) == check_status([error, warning]) == "error"
    assert CheckReport.failure_message([passed, warning, error]) == "Проверки готовых документов не пройдены: warning, error"


def test_report_uses_supplied_scale_without_svg(route_data, config, tmp_path):
    project = Project.model_validate(route_data)
    report = CheckReport(project, config, [
        CheckResult("profile_point_spacing", Status.WARNING, "Тесные подписи"),
    ], vertical_scale=200)

    assert report.write(tmp_path) == "warning"

    text = (tmp_path / "check_report.md").read_text(encoding="utf-8")
    assert "Результат выпуска: **warning**" in text
    assert "Труба ⌀110 при 1:200 = 0,55 мм < 2 мм" in text
    assert "| profile_point_spacing | Предупреждение | Тесные подписи |" in text
    assert "Замечания к исходным данным" not in text
    assert MISSING_PIPE_STANDARD_NOTE in text
    project.pipe.standard = "ТУ TEST"
    assert MISSING_PIPE_STANDARD_NOTE not in report.missing_data()
