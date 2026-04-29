import io

import pytest
from docx import Document

from app.auth.session import create_session
from app.db.models import User


def _docx_bytes(text: str = "Hello World", heading: str = "My Title") -> bytes:
    doc = Document()
    doc.add_paragraph(heading, style="Heading 1")
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


@pytest.fixture
def auth_client(app_client, db_session):
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    sid = create_session(db_session, u.id)
    app_client.cookies.set("applicator_session", sid)
    return app_client, u


def test_create_and_list_cv(auth_client):
    c, _ = auth_client
    r = c.post("/api/cv-variants", json={"name": "default", "source_md": "x", "is_default": True})
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "default" and body["is_default"] is True
    r2 = c.get("/api/cv-variants")
    assert len(r2.json()) == 1


def test_set_default_exclusive(auth_client):
    c, _ = auth_client
    a = c.post("/api/cv-variants", json={"name": "a", "source_md": "x", "is_default": True}).json()
    b = c.post("/api/cv-variants", json={"name": "b", "source_md": "y", "is_default": True}).json()
    items = c.get("/api/cv-variants").json()
    flags = {it["id"]: it["is_default"] for it in items}
    assert flags[a["id"]] is False
    assert flags[b["id"]] is True


def test_anschreiben_endpoints(auth_client):
    c, _ = auth_client
    r = c.post("/api/anschreiben-variants", json={"name": "t", "source_md": "tpl"})
    assert r.status_code == 200
    assert c.get("/api/anschreiben-variants").json()[0]["name"] == "t"


def test_upload_cv_docx_creates_variant_and_marks_default(auth_client):
    c, _ = auth_client
    data = _docx_bytes(text="Worked at Acme", heading="My CV")
    r = c.post(
        "/api/cv-variants/upload",
        files={"file": ("cv-de.docx", data,
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "cv-de"
    assert body["is_default"] is True
    assert "# My CV" in body["source_md"]
    assert "Worked at Acme" in body["source_md"]


def test_second_upload_does_not_become_default(auth_client):
    c, _ = auth_client
    data = _docx_bytes()
    c.post("/api/cv-variants/upload", files={"file": ("first.docx", data, "x")})
    r = c.post("/api/cv-variants/upload", files={"file": ("second.docx", data, "x")})
    assert r.status_code == 200
    assert r.json()["is_default"] is False


def test_upload_rejects_non_docx(auth_client):
    c, _ = auth_client
    r = c.post(
        "/api/cv-variants/upload",
        files={"file": ("plain.txt", b"hello", "text/plain")},
    )
    assert r.status_code == 400


def test_upload_anschreiben(auth_client):
    c, _ = auth_client
    data = _docx_bytes(text="Sehr geehrte Damen und Herren", heading="Anschreiben")
    r = c.post(
        "/api/anschreiben-variants/upload",
        files={"file": ("anschreiben-de.docx", data, "x")},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "anschreiben-de"
    assert "Sehr geehrte" in body["source_md"]
