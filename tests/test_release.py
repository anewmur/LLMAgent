from xml.etree import ElementTree as ET

import pytest
from pypdf import PdfReader
import yaml

from core.documents import DocumentSet
from core.package_checks import PackageChecks
from core.release import CONFIG_PATH, create_package
from core.validate import validate_input


NS = {"s": "http://www.w3.org/2000/svg"}


def test_release_uses_project_and_detects_tampering(route_data, tmp_path):
    folder = tmp_path / "output"
    for x, diameter, length in [(280, 110, "360,00"), (300, 160, "380,00")]:
        for stale in ["old.svg", "changes.md", "pdf/NV.pdf", "old/nested/preview.png"]:
            path = folder / stale
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old release")
        route_data["points"][-1]["x"] = x
        route_data["pipe"]["outer_diameter_mm"] = diameter
        route_data["object"].update(project_code="OTHER-07", name="Другой объект $100 & участок")
        project, _ = validate_input(route_data)
        result = create_package(project, folder)
        assert result["status"] == "ok", result
        assert all(c["passed"] for c in result["checks"])
        expected = {"general.svg", "plan.svg", "profile.svg", "specification.svg", "specification.csv", "check_report.md"}
        expected.update("pdf/" + name + ".pdf" for name in ["general", "plan", "profile", "specification", "package"])
        assert {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} == expected
        assert {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_dir()} == {"pdf"}
        report = (folder / "check_report.md").read_text(encoding="utf-8")
        assert "## Допущения" in report and "## Ограничения" in report
        assert "Отводы включены в спецификацию вопреки ГОСТ 21.704 п. 7.4" in report
        assert f"Труба ⌀{diameter} при 1:100" in report
        assert length in (folder / "specification.csv").read_text(encoding="utf-8-sig")
        assert len(PdfReader(folder / "pdf/package.pdf").pages) == 4
        for stem, number, total in [("general", "1", "3"), ("plan", "2", ""), ("profile", "3", ""), ("specification", "", "1")]:
            root = ET.parse(folder / (stem + ".svg")).getroot()
            assert root.get("viewBox") == "0 0 420 297"
            assert {float(e.get("font-size")) for e in root.iter() if e.get("font-size")} <= {2.5, 3.5, 5, 7, 10, 14}
            assert (root.find(".//s:text[@x='157.5'][@y='36.5']", NS).text or "") == number
            assert (root.find(".//s:text[@x='175'][@y='36.5']", NS).text or "") == total
            page = PdfReader(folder / "pdf" / (stem + ".pdf")).pages[0]
            assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(420, abs=0.02)
            assert float(page.mediabox.height) * 25.4 / 72 == pytest.approx(297, abs=0.02)
    path = folder / "profile.svg"
    value = ET.parse(path).getroot().find(".//s:text[@data-kind='bottom-level']", NS).text
    path.write_text(path.read_text(encoding="utf-8").replace(f'>{value}<', '>999,99<'), encoding="utf-8")
    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    checks = PackageChecks(project, DocumentSet(project, config), folder).run()
    assert not next(c["passed"] for c in checks if c["id"] == "profile_values")


@pytest.mark.parametrize("case", ["missing_level", "material_conflict", "bend_conflict"])
def test_invalid_project_does_not_replace_documents(route_data, tmp_path, case):
    project, _ = validate_input(route_data)
    folder = tmp_path / "output"
    assert create_package(project, folder)["status"] == "ok"
    before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    if case == "missing_level":
        project.points[3].axis = None
    elif case == "material_conflict":
        project.pipe.material = "ПЭ 80"
    else:
        project.bends[0].angle_deg = 45
    result = create_package(project, folder)
    assert result["status"] == "error" and result["problems"]
    assert {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()} == before
