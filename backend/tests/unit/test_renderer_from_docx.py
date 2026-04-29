import io

from docx import Document

from app.renderer.from_docx import docx_bytes_to_markdown


def _make_docx(paragraphs: list[tuple[str, str | None]]) -> bytes:
    """Build a docx in-memory. Each tuple is (text, style_or_None)."""
    doc = Document()
    for text, style in paragraphs:
        if style:
            doc.add_paragraph(text, style=style)
        else:
            doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def test_converts_paragraphs_to_markdown():
    data = _make_docx(
        [
            ("My CV", "Heading 1"),
            ("Experience", "Heading 2"),
            ("Worked at Acme", None),
        ]
    )
    md = docx_bytes_to_markdown(data)
    assert "# My CV" in md
    assert "## Experience" in md
    assert "Worked at Acme" in md


def test_strips_outer_whitespace():
    data = _make_docx([("Hello", None)])
    md = docx_bytes_to_markdown(data)
    assert md == "Hello"
