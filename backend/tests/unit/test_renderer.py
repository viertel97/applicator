from pathlib import Path

from docx import Document

from app.renderer import to_docx, to_html


def test_to_docx_writes_file(tmp_path: Path):
    out = tmp_path / "out.docx"
    p = to_docx("# Title\n\nHello world\n\n- one\n- two", out)
    assert p.exists()
    doc = Document(str(p))
    texts = [par.text for par in doc.paragraphs]
    assert "Title" in texts
    assert "Hello world" in texts
    assert "one" in texts


def test_to_html():
    h = to_html("# Hi")
    assert "<h1>" in h
