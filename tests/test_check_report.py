from core.assumptions import load_assumptions
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
    ], load_assumptions(config, project, 200))

    assert report.write(tmp_path) == "warning"

    text = (tmp_path / "check_report.md").read_text(encoding="utf-8")
    assert "Результат выпуска: **warning**" in text
    assert "Труба ⌀110 при 1:200 = 0,55 мм < 2 мм" in text
    assert "| profile_point_spacing | Предупреждение | Тесные подписи |" in text
    assert "Замечания к исходным данным" not in text
    assert config["missing_data"]["pipe_standard"] in text
    project.pipe.standard = "ТУ TEST"
    assert config["missing_data"]["pipe_standard"] not in report.missing_data()


def test_pipe_note_uses_explicit_scale_and_line_wording(route_data, config):
    route_data["pipe"].update(outer_diameter_mm=250, wall_mm=14.8)
    project = Project.model_validate(route_data)
    for scale, wording in [(100, "двумя линиями"), (200, "одной линией")]:
        items = load_assumptions(config, project, scale)
        note = next(item for item in items if item.id == "pipe_note")
        assert note.short == f"Труба ⌀250 на профиле — {wording}"
        assert not note.key
        assert "slope_direction" not in [item.id for item in items]
