from xml.etree import ElementTree as ET

from core.documents import DocumentSet
from core.models import DocumentId, Project
from core.plan import PlanDrawing
from core.profile import ProfileDrawing
from core.sheet import Sheet
from core.specification import SpecificationDrawing


def test_sheet_substitutes_requisites():
    title = "План трассы & профиль"
    designation = "OTHER-02-НВ"
    object_name = "Другой объект $100 ${title} & участок"
    sheet = Sheet(designation, object_name, title, total=4)
    sheet.number = 2
    svg = sheet.render()
    root = ET.fromstring(svg)
    ns = {"svg": "http://www.w3.org/2000/svg"}

    texts = ["".join(element.itertext()) for element in root.findall(".//svg:text", ns)]
    assert designation in texts
    assert "AI-TEST-01" not in svg
    assert title in texts
    assert "2" in texts
    assert object_name in texts
    assert "Листов" in texts
    assert "4" in texts


def test_drawings_take_requisites_from_document_set(route_data, config):
    project = Project.model_validate(route_data)
    for document in config["documents"]:
        if document["id"] != "report":
            document["title"] = f'Лист {document["id"]} $1 & {{буква}}'
            document["suffix"] = f'-TEST-{document["id"]}'
    documents = DocumentSet(project, config)

    for document_id, drawing_class in [
        (DocumentId.PLAN, PlanDrawing),
        (DocumentId.PROFILE, ProfileDrawing),
        (DocumentId.SPECIFICATION, SpecificationDrawing),
    ]:
        document = documents.get(document_id)
        drawing = drawing_class(project, document)
        root = ET.fromstring(drawing.render())
        text = "".join("".join(root.itertext()).split())
        assert document["designation"] in text
        assert "".join(document["title"].split()) in text
        if document_id == DocumentId.PLAN:
            assert drawing.sheet.title == document["title"] + " (1:1000)"
        else:
            assert drawing.sheet.title == document["title"]
