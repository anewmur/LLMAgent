from copy import deepcopy
from xml.etree import ElementTree as ET
import csv

from core.documents import DocumentSet
from core.formatting import format_pipe_value
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.models import DocumentId
from core.session import RouteSession
from core.specification import HEADERS, SpecificationDrawing
from core.validate import validate_input
import core.sheet as sheet_module
import core.specification as specification_module


def test_csv_and_svg_match_calculated_quantities(route_data, tmp_path, config):
    # \u0418\u0441\u0445\u043e\u0434\u043d\u044b\u0439 \u043f\u0440\u0438\u043c\u0435\u0440 \u0438 \u0434\u0440\u0443\u0433\u043e\u0439 \u0448\u0438\u0444\u0440, \u043e\u0431\u044a\u0435\u043a\u0442, \u0434\u0438\u0430\u043c\u0435\u0442\u0440 \u0438 \u0434\u043b\u0438\u043d\u0430 \u2014 \u0431\u0435\u0437 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u043a\u043e\u0434\u0430.
    for code, name, p5_x, diameter, wall, expected_length, standard in [
        ("AI-TEST-01", "\u0423\u0447\u0435\u0431\u043d\u044b\u0439 \u0443\u0447\u0430\u0441\u0442\u043e\u043a \u0432\u043e\u0434\u043e\u043f\u0440\u043e\u0432\u043e\u0434\u0430", 280, 110, 6.6, 360, None),
        ("OTHER-02", "Другой объект $100 ${table_body} & участок", 300, 160, 9.5, 380,
         "\u0422\u0423 TEST-160. \u0422\u0440\u0443\u0431\u044b \u043d\u0430\u043f\u043e\u0440\u043d\u044b\u0435 \u043f\u043e\u043b\u0438\u044d\u0442\u0438\u043b\u0435\u043d\u043e\u0432\u044b\u0435. \u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0443\u0441\u043b\u043e\u0432\u0438\u044f"),
    ]:
        data = deepcopy(route_data)
        data["object"].update(project_code=code, name=name)
        data["points"][-1]["x"] = p5_x
        data["pipe"].update(outer_diameter_mm=diameter, wall_mm=wall)
        if standard is None:
            data["pipe"].pop("standard", None)  # \u041f\u043e\u043b\u0435 \u043c\u043e\u0436\u0435\u0442 \u0432\u043e\u043e\u0431\u0449\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c.
        else:
            data["pipe"]["standard"] = standard
        project, problems = validate_input(data)
        assert not problems
        output = tmp_path / code

        drawing = SpecificationDrawing(project, DocumentSet(project, config).get(DocumentId.SPECIFICATION))
        svg = drawing.render()
        drawing.write_csv(output / "specification.csv")
        (output / "specification.svg").write_text(svg, encoding="utf-8")

        with (output / "specification.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=";")
            assert reader.fieldnames == HEADERS
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0438 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0430"] == f"\u041e\u0442\u0432\u043e\u0434 90\u00b0 \u041f\u042d 100 SDR 17 {diameter}"
        assert rows[0]["\u041f\u0440\u0438\u043c\u0435\u0447\u0430\u043d\u0438\u0435"] == "\u041c\u0430\u0442\u0435\u0440\u0438\u0430\u043b \u0438 SDR \u043f\u0440\u0438\u043d\u044f\u0442\u044b \u043a\u0430\u043a \u0443 \u0442\u0440\u0443\u0431\u044b"
        assert rows[0]["\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e"] == "2"
        assert rows[0]["\u0415\u0434. \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f"] == "\u0448\u0442."
        assert rows[1]["\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0438 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0430"] == f"\u0422\u0440\u0443\u0431\u0430 \u041f\u042d 100 SDR 17 {diameter}\u00d7{format_pipe_value(wall)}"
        assert rows[1]["\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e"] == f"{expected_length},00"
        assert rows[1]["\u0415\u0434. \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f"] == "\u043c"
        assert rows[0][HEADERS[2]] == ""
        assert rows[1][HEADERS[2]] == (standard or "")
        for row in rows:
            for field in ["\u041a\u043e\u0434 \u043f\u0440\u043e\u0434\u0443\u043a\u0446\u0438\u0438", "\u041f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a", "\u041c\u0430\u0441\u0441\u0430 1 \u0435\u0434., \u043a\u0433"]:
                assert row[field] == ""

        root = ET.parse(output / "specification.svg").getroot()
        ns = {"s": "http://www.w3.org/2000/svg"}
        texts = [" ".join(element.itertext()) for element in root.findall(".//s:text", ns)]
        assert code + "-\u041d\u0412.\u0421\u041e" in texts
        assert name in texts
        table = root.find("s:g[@id='specification-table']", ns)
        previous_bottom = None
        for index in range(1, len(rows) + 1):
            svg_row = table.find(f"s:g[@id='spec-row-{index}']", ns)
            # \u041f\u0435\u0440\u0435\u043d\u0435\u0441\u0451\u043d\u043d\u044b\u0435 \u043f\u0440\u0438\u043c\u0435\u0447\u0430\u043d\u0438\u044f \u0438 \u0434\u043b\u0438\u043d\u043d\u044b\u0439 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442 \u043d\u0435 \u043d\u0430\u0435\u0437\u0436\u0430\u044e\u0442 \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0443\u044e \u0441\u0442\u0440\u043e\u043a\u0443.
            text_y = [float(element.get("y")) for element in svg_row.findall("s:text", ns)]
            if previous_bottom is not None:
                assert previous_bottom + DEFAULT_FONT_SIZE_MM <= min(text_y)
            previous_bottom = max(text_y)
        assert {path.suffix for path in output.iterdir()} == {".csv", ".svg"}


def test_conflicting_materials_prevent_specification_export(route_data, tmp_path, config, write_route):
    data = deepcopy(route_data)
    data["pipe"]["material"] = "\u041f\u042d 80"
    input_file = write_route(data)
    output = tmp_path / "output"

    result = RouteSession(input_file, output, config).release()

    assert result["status"] == "error"
    assert any(problem["where"] == "pipe" for problem in result["problems"])
    assert not output.exists()


def test_specification_uses_shared_sheet_and_column_widths(route_data, tmp_path, monkeypatch, config):
    template = sheet_module.TEMPLATE_PATH.read_text(encoding="utf-8")
    template = template.replace('id="title-block"', 'id="title-block" data-shared="yes"')
    shared_path = tmp_path / "sheet.svg"
    shared_path.write_text(template, encoding="utf-8")
    monkeypatch.setattr(sheet_module, "TEMPLATE_PATH", shared_path)
    monkeypatch.setattr(specification_module, "WIDTHS", [25, 125, 60, 35, 45, 20, 20, 25, 40])
    title = "Ведомость $100"
    project, problems = validate_input(route_data)
    assert not problems
    drawing = SpecificationDrawing(project, DocumentSet(project, config).get(DocumentId.SPECIFICATION))
    drawing.sheet.title, drawing.sheet.number, drawing.sheet.total = title, 2, 7

    root = ET.fromstring(drawing.render())
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.find("s:g/s:rect[@id='title-block']", ns).get("data-shared") == "yes"
    assert root.find(".//s:text[@x='157.5'][@y='36.5']", ns).text == "2"
    assert root.find(".//s:text[@x='175'][@y='36.5']", ns).text == "7"
    assert title in ["".join(element.itertext()) for element in root.findall(".//s:text", ns)]
    table = root.find("s:g[@id='specification-table']", ns)
    assert table.find("s:path[@d='M 45,30 V 222']", ns) is not None
    assert table.find("s:text[@x='32.5']", ns).text == "Поз."
    first_row = table.find("s:g[@id='spec-row-1']", ns)
    assert first_row.find("s:text[@x='32.5']", ns).text == "1"
