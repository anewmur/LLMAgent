import pytest
from pypdf import PdfReader

from core.sheet import svg_to_pdf
from core.sheet import create_sheet


def test_pdf_preserves_a3_dimensions_and_cyrillic(tmp_path):
    svg_path = tmp_path / "sheet.svg"
    pdf_path = tmp_path / "sheet.pdf"
    svg_path.write_text(
        create_sheet("OTHER-02-НВ", "Другой объект", "План трассы", 1, 4),
        encoding="utf-8",
    )

    svg_to_pdf(svg_path, pdf_path)

    reader = PdfReader(pdf_path)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(420, abs=0.01)
    assert float(page.mediabox.height) * 25.4 / 72 == pytest.approx(297, abs=0.01)
    text = page.extract_text()
    for expected in ["OTHER-02-НВ", "Другой объект", "План трассы", "Листов", "УЧЕБНЫЙ КОМПЛЕКТ"]:
        assert expected in text
