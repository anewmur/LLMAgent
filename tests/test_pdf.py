import pytest
from pypdf import PdfReader

from core.sheet import svg_to_pdf
from core.sheet import Sheet


def test_pdf_preserves_a3_dimensions_and_cyrillic(tmp_path, monkeypatch):
    svg_path = tmp_path / "sheet.svg"
    pdf_path = tmp_path / "sheet.pdf"
    svg = Sheet("OTHER-02-НВ", "Другой объект", "План трассы", 1, 4).render()
    label = '<text x="30" y="60" font-family="DejaVu Sans" font-size="5">В1 ⌀110×6,6</text>'
    svg_path.write_text(svg.replace('</svg>', label + '</svg>'), encoding="utf-8")
    monkeypatch.setenv("WINDIR", str(tmp_path / "no_system_fonts"))

    svg_to_pdf(svg_path, pdf_path)

    reader = PdfReader(pdf_path)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    assert float(page.mediabox.width) * 25.4 / 72 == pytest.approx(420, abs=0.01)
    assert float(page.mediabox.height) * 25.4 / 72 == pytest.approx(297, abs=0.01)
    text = page.extract_text()
    for expected in ["OTHER-02-НВ", "Другой объект", "План трассы", "Листов", "УЧЕБНЫЙ КОМПЛЕКТ", "⌀110×6,6"]:
        assert expected in text
    fonts = page["/Resources"]["/Font"].values()
    assert any("DejaVuSans" in str(font.get_object().get("/BaseFont")) for font in fonts)
