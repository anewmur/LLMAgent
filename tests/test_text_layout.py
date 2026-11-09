from xml.etree import ElementTree as ET
import re

from core.assumptions import load_assumptions
from core.documents import DocumentSet
from core.drawing_settings import DEFAULT_FONT_SIZE_MM
from core.general import GeneralData
from core.models import DocumentId, Project
from core.specification import SpecificationDrawing


NS = {"s": "http://www.w3.org/2000/svg"}


def text_boxes(element, origin_x=0, font_size=DEFAULT_FONT_SIZE_MM, anchor="start"):
    """Возвращает горизонтальные габариты строк с учётом шрифта, выравнивания и translate."""
    font_size = float(element.get("font-size", font_size))
    anchor = element.get("text-anchor", anchor)
    transform = element.get("transform")
    if transform:
        translation = re.fullmatch(r"translate\(([-\d.]+)[ ,]+([-\d.]+)\)", transform)
        assert translation is not None, transform
        origin_x += float(translation.group(1))
    if element.tag in {f'{{{NS["s"]}}}text', f'{{{NS["s"]}}}tspan'} and (element.text or "").strip():
        width = len(element.text) * 0.6 * font_size
        anchor_x = origin_x + float(element.get("x"))
        offset = width / 2 if anchor == "middle" else width if anchor == "end" else 0
        yield element, anchor_x, anchor_x - offset, anchor_x - offset + width
    for child in element:
        yield from text_boxes(child, origin_x, font_size, anchor)


def assert_inside_columns(boxes, boundaries):
    """Проверяет, что каждая строка помещается в графе с её точкой привязки."""
    for element, anchor_x, left, right in boxes:
        column_left, column_right = next(
            (start, end) for start, end in zip(boundaries, boundaries[1:]) if start <= anchor_x <= end
        )
        assert column_left <= left and right <= column_right, element.text


def test_general_text_stays_inside_columns_and_frame(route_data, config):
    project = Project.model_validate(route_data)
    root = ET.fromstring(GeneralData(project, DocumentSet(project, config), config, load_assumptions(config, project, 100)).render())
    frame = root.find("s:g/s:rect[@id='frame']", NS)
    frame_left = float(frame.get("x"))
    frame_right = frame_left + float(frame.get("width"))
    for element, anchor_x, left, right in text_boxes(root):
        assert frame_left <= left and right <= frame_right, element.text

    general = root.find("s:g[@id='general-data']", NS)
    for wrapper in general:
        table = wrapper.find("s:g", NS)
        if table is None or table.find("s:rect", NS) is None:
            continue
        table_left = float(re.search(r"translate\(([-\d.]+)", wrapper.get("transform")).group(1))
        width = float(table.find("s:rect", NS).get("width"))
        grid = table.find("s:path", NS).get("d")
        separators = [float(value) for value in re.findall(r"M ([-\d.]+),0 V", grid)]
        boundaries = [table_left + value for value in [0, *separators, width]]
        assert_inside_columns(text_boxes(wrapper), boundaries)

    for element, anchor_x, left, right in text_boxes(general.find("s:g[@id='general-assumptions']", NS)):
        assert right <= frame_right - 3, element.text
    notes = general.find("s:g[@id='general-notes']", NS)
    drawing_register = general.find("s:g[@id='drawing-register']", NS)
    register_left = float(re.search(r"translate\(([-\d.]+)", drawing_register.get("transform")).group(1))
    notes_right = register_left + float(drawing_register.find("s:g/s:rect", NS).get("width"))
    for element, anchor_x, left, right in text_boxes(notes):
        assert right <= notes_right, element.text
    fifth_note = " ".join(" ".join(notes.findall("s:text", NS)[4].itertext()).split())
    assert fifth_note == ("В исходных данных заданы отметки оси трубопровода; на профиле показаны отметки низа трубы "
                          "(ось минус половина наружного диаметра). Труба ⌀110 на профиле — одной линией. Линии трубы — сплошные толстые.")


def test_specification_header_text_stays_inside_columns(route_data, config):
    project = Project.model_validate(route_data)
    document = DocumentSet(project, config).get(DocumentId.SPECIFICATION)
    root = ET.fromstring(SpecificationDrawing(project, document).render())
    table = root.find("s:g[@id='specification-table']", NS)
    rectangle = table.find("s:rect", NS)
    table_left = float(rectangle.get("x"))
    table_top = float(rectangle.get("y"))
    table_right = table_left + float(rectangle.get("width"))
    separators = [float(match.group(1)) for path in table.findall("s:path", NS)
                  if (match := re.fullmatch(rf"M ([-\d.]+),{table_top:g} V [-\d.]+", path.get("d")))]
    boundaries = [table_left, *separators, table_right]
    headers = table.findall("s:text", NS)
    for header in headers:
        assert_inside_columns(text_boxes(header, font_size=float(table.get("font-size"))), boundaries)
    assert {"Коли-", "чество"} <= {header.text for header in headers}
