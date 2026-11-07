from pypdf import PdfReader

from core.sheet import svg_to_pdf
from core.sheet import Sheet


def test_pdf_preserves_requisites_and_cyrillic(tmp_path):
    svg_path = tmp_path / "sheet.svg"
    pdf_path = tmp_path / "sheet.pdf"
    sheet = Sheet("OTHER-02-НВ", "Другой объект", "План трассы", total=4)
    sheet.number = 1
    svg_path.write_text(sheet.render(), encoding="utf-8")

    svg_to_pdf(svg_path, pdf_path)

    reader = PdfReader(pdf_path)
    page = reader.pages[0]
    text = page.extract_text()
    for expected in ["OTHER-02-НВ", "Другой объект", "План трассы", "Листов"]:
        assert expected in text
