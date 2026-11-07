from core.assumptions import MISSING_PIPE_STANDARD_NOTE
from core.check_report import CheckReport, check_status
from core.models import Project


def test_check_status_prioritizes_failed_errors():
    passed = {"passed": True, "level": "error"}
    warning = {"passed": False, "level": "warning"}
    error = {"passed": False, "level": "error"}
    assert check_status([]) == "ok"
    assert check_status([passed]) == "ok"
    assert check_status([passed, warning]) == "warning"
    assert check_status([warning, error]) == check_status([error, warning]) == "error"


def test_report_uses_supplied_scale_without_svg(route_data, config, tmp_path):
    project = Project.model_validate(route_data)
    report = CheckReport(project, config, [{
        "id": "profile_point_spacing", "passed": False, "level": "warning", "detail": "Тесные подписи",
    }], vertical_scale=200)

    assert report.write(tmp_path) == "warning"

    text = (tmp_path / "check_report.md").read_text(encoding="utf-8")
    assert "Результат выпуска: **warning**" in text
    assert "Труба ⌀110 при 1:200 = 0,55 мм < 2 мм" in text
    assert "| profile_point_spacing | Предупреждение | Тесные подписи |" in text
    assert "Замечания к исходным данным" not in text
    assert MISSING_PIPE_STANDARD_NOTE in text
    project.pipe.standard = "ТУ TEST"
    assert MISSING_PIPE_STANDARD_NOTE not in report.missing_data()
