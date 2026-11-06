from xml.etree import ElementTree as ET

from core.sheet import create_sheet


def test_a3_sheet_template():
    title = "План трассы & профиль"
    designation = "OTHER-02-НВ"
    object_name = "Другой объект & участок"
    svg = create_sheet(designation, object_name, title, 2, 4)
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}

    assert root.attrib == {
        "width": "420mm", "height": "297mm", "viewBox": "0 0 420 297",
    }
    frame = root.find("svg:g/svg:rect[@id='frame']", ns)
    assert (frame.get("x"), frame.get("y"), frame.get("width"), frame.get("height")) == (
        "20", "5", "395", "287",
    )
    block = root.find("svg:g/svg:rect[@id='title-block']", ns)
    assert (block.get("x"), block.get("y"), block.get("width"), block.get("height")) == (
        "230", "237", "185", "55",
    )
    texts = ["".join(element.itertext()) for element in root.findall(".//svg:text", ns)]
    assert designation in texts
    assert "AI-TEST-01" not in svg
    assert title in texts
    assert "2" in texts
    assert object_name in texts
    assert "Листов" in texts
    assert "4" in texts
    assert "УЧЕБНЫЙ КОМПЛЕКТ" in texts
