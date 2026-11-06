import csv
import json
from xml.etree import ElementTree as ET

import core.sheet as sheet_module
import core.specification as specification_module
from core.calculations import calculate_route_length
from core.specification import HEADERS, Specification, create_specification


def test_csv_and_svg_match_calculated_quantities(route_data, tmp_path):
    # \u0418\u0441\u0445\u043e\u0434\u043d\u044b\u0439 \u043f\u0440\u0438\u043c\u0435\u0440 \u0438 \u0434\u0440\u0443\u0433\u043e\u0439 \u0448\u0438\u0444\u0440, \u043e\u0431\u044a\u0435\u043a\u0442, \u0434\u0438\u0430\u043c\u0435\u0442\u0440 \u0438 \u0434\u043b\u0438\u043d\u0430 \u2014 \u0431\u0435\u0437 \u0438\u0437\u043c\u0435\u043d\u0435\u043d\u0438\u044f \u043a\u043e\u0434\u0430.
    for code, name, p5_x, diameter, expected_length, standard in [
        ("AI-TEST-01", "\u0423\u0447\u0435\u0431\u043d\u044b\u0439 \u0443\u0447\u0430\u0441\u0442\u043e\u043a \u0432\u043e\u0434\u043e\u043f\u0440\u043e\u0432\u043e\u0434\u0430", 280, 110, 360, None),
        ("OTHER-02", "Другой объект $100 ${table_body} & участок", 300, 160, 380,
         "\u0422\u0423 TEST-160. \u0422\u0440\u0443\u0431\u044b \u043d\u0430\u043f\u043e\u0440\u043d\u044b\u0435 \u043f\u043e\u043b\u0438\u044d\u0442\u0438\u043b\u0435\u043d\u043e\u0432\u044b\u0435. \u0422\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0438\u0435 \u0443\u0441\u043b\u043e\u0432\u0438\u044f"),
    ]:
        data = json.loads(json.dumps(route_data))
        data["object"].update(project_code=code, name=name)
        data["points"][-1]["x"] = p5_x
        data["pipe"]["outer_diameter_mm"] = diameter
        if standard is None:
            data["pipe"].pop("standard", None)  # \u041f\u043e\u043b\u0435 \u043c\u043e\u0436\u0435\u0442 \u0432\u043e\u043e\u0431\u0449\u0435 \u043e\u0442\u0441\u0443\u0442\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c.
        else:
            data["pipe"]["standard"] = standard
        input_file = tmp_path / "input.json"
        input_file.write_text(json.dumps(data), encoding="utf-8")
        output = tmp_path / code

        result = create_specification(input_file, output)

        assert result["status"] == "ok"
        with (output / "specification.csv").open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, delimiter=";")
            assert reader.fieldnames == HEADERS
            rows = list(reader)
        assert len(rows) == 2
        assert rows[0]["\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0438 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0430"] == f"\u041e\u0442\u0432\u043e\u0434 90\u00b0 \u041f\u042d 100 SDR 17 {diameter}"
        assert rows[0]["\u041f\u0440\u0438\u043c\u0435\u0447\u0430\u043d\u0438\u0435"] == "\u041c\u0430\u0442\u0435\u0440\u0438\u0430\u043b \u0438 SDR \u043f\u0440\u0438\u043d\u044f\u0442\u044b \u043a\u0430\u043a \u0443 \u0442\u0440\u0443\u0431\u044b"
        assert rows[0]["\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e"] == "2"
        assert rows[0]["\u0415\u0434. \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f"] == "\u0448\u0442."
        assert rows[1]["\u041d\u0430\u0438\u043c\u0435\u043d\u043e\u0432\u0430\u043d\u0438\u0435 \u0438 \u0442\u0435\u0445\u043d\u0438\u0447\u0435\u0441\u043a\u0430\u044f \u0445\u0430\u0440\u0430\u043a\u0442\u0435\u0440\u0438\u0441\u0442\u0438\u043a\u0430"] == f"\u0422\u0440\u0443\u0431\u0430 \u041f\u042d 100 SDR 17 {diameter}\u00d76,6"
        assert rows[1]["\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e"] == f"{expected_length},00"
        assert rows[1]["\u0415\u0434. \u0438\u0437\u043c\u0435\u0440\u0435\u043d\u0438\u044f"] == "\u043c"
        assert rows[0][HEADERS[2]] == ""
        assert rows[1][HEADERS[2]] == (standard or "")
        assert float(rows[1]["\u041a\u043e\u043b\u0438\u0447\u0435\u0441\u0442\u0432\u043e"].replace(",", ".")) == calculate_route_length(input_file)["length_m"]
        for row in rows:
            for field in ["\u041a\u043e\u0434 \u043f\u0440\u043e\u0434\u0443\u043a\u0446\u0438\u0438", "\u041f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a", "\u041c\u0430\u0441\u0441\u0430 1 \u0435\u0434., \u043a\u0433"]:
                assert row[field] == ""

        root = ET.parse(output / "specification.svg").getroot()
        ns = {"s": "http://www.w3.org/2000/svg"}
        assert root.get("viewBox") == "0 0 420 297"
        texts = [" ".join(e.itertext()) for e in root.findall(".//s:text", ns)]
        assert code + "-\u041d\u0412.\u0421\u041e" in texts
        assert name in texts
        assert "\u0423\u0427\u0415\u0411\u041d\u042b\u0419 \u041a\u041e\u041c\u041f\u041b\u0415\u041a\u0422" in texts
        table = root.find("s:g[@id='specification-table']", ns)
        assert table.find("s:rect", ns).get("width") == "395"
        previous_bottom = None
        for i, row in enumerate(rows, start=1):
            svg_row = table.find(f"s:g[@id='spec-row-{i}']", ns)
            row_text = " ".join(" ".join(svg_row.itertext()).split())
            for value in row.values():
                if value:
                    assert value in row_text
            # \u041f\u0435\u0440\u0435\u043d\u0435\u0441\u0451\u043d\u043d\u044b\u0435 \u043f\u0440\u0438\u043c\u0435\u0447\u0430\u043d\u0438\u044f \u0438 \u0434\u043b\u0438\u043d\u043d\u044b\u0439 \u0441\u0442\u0430\u043d\u0434\u0430\u0440\u0442 \u043d\u0435 \u043d\u0430\u0435\u0437\u0436\u0430\u044e\u0442 \u043d\u0430 \u0441\u043b\u0435\u0434\u0443\u044e\u0449\u0443\u044e \u0441\u0442\u0440\u043e\u043a\u0443.
            text_y = [float(e.get("y")) for e in svg_row.findall("s:text", ns)]
            if previous_bottom is not None:
                assert previous_bottom + 3.5 <= min(text_y)
            previous_bottom = max(text_y)
        assert {p.suffix for p in output.iterdir()} == {".csv", ".svg"}


def test_conflicting_materials_prevent_specification_export(route_data, tmp_path):
    data = json.loads(json.dumps(route_data))
    data["pipe"]["material"] = "\u041f\u042d 80"
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps(data), encoding="utf-8")
    output = tmp_path / "output"

    result = create_specification(input_file, output)

    assert result["status"] == "error"
    assert any(p["where"] == "pipe" for p in result["problems"])
    assert not output.exists()


def test_specification_uses_shared_sheet_and_column_widths(input_file, tmp_path, monkeypatch):
    template = sheet_module.TEMPLATE_PATH.read_text(encoding="utf-8")
    template = template.replace('id="title-block"', 'id="title-block" data-shared="yes"')
    shared_path = tmp_path / "sheet.svg"
    shared_path.write_text(template, encoding="utf-8")
    monkeypatch.setattr(sheet_module, "TEMPLATE_PATH", shared_path)
    monkeypatch.setattr(specification_module, "WIDTHS", [25, 125, 60, 35, 45, 20, 20, 25, 40])
    title = "Ведомость $100"
    result = Specification(input_file, title=title, number=2, total=7).create(tmp_path / "output")

    assert result["status"] == "ok"
    root = ET.parse(result["files"]["svg"]).getroot()
    ns = {"s": "http://www.w3.org/2000/svg"}
    assert root.find("s:g/s:rect[@id='title-block']", ns).get("data-shared") == "yes"
    assert root.find(".//s:text[@x='157.5'][@y='36.5']", ns).text == "2"
    assert root.find(".//s:text[@x='175'][@y='36.5']", ns).text == "7"
    assert title in ["".join(e.itertext()) for e in root.findall(".//s:text", ns)]
    table = root.find("s:g[@id='specification-table']", ns)
    assert table.find("s:rect", ns).get("width") == "395"
    assert table.find("s:path[@d='M 45,30 V 222']", ns) is not None
    assert table.find("s:text[@x='32.5']", ns).text == "Поз."
    first_row = table.find("s:g[@id='spec-row-1']", ns)
    assert first_row.find("s:text[@x='32.5']", ns).text == "1"
