from unittest.mock import MagicMock

from app.db.models import Application, JobPosting, User
from app.extractor.schemas import ContactInfo, ExtractedJobPosting
from app.pipeline.extract import run_extract


def _user(db):
    u = User(ms_oid="oid1", email="u@x.com", display_name="U")
    db.add(u)
    db.flush()
    return u


def test_run_extract_writes_contact_block(db_session, monkeypatch):
    u = _user(db_session)
    app = Application(user_id=u.id, url="https://x.com/1", url_hash="h" * 64)
    db_session.add(app)
    db_session.commit()

    fake = ExtractedJobPosting(
        title="Eng", company="Acme", language="en",
        contact=ContactInfo(name="Jane", email="j@x.com", phone="+49 30 1"),
    )
    monkeypatch.setattr("app.pipeline.extract.extract", lambda *_a, **_k: fake)

    run_extract(db_session, app, "raw", "/tmp/raw.html", MagicMock())
    db_session.refresh(app)
    jp = db_session.query(JobPosting).filter_by(application_id=app.id).one()
    assert jp.contact == {
        "name": "Jane", "role": None, "email": "j@x.com", "phone": "+49 30 1",
    }
