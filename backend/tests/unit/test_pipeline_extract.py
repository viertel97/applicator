import json
import uuid
from unittest.mock import MagicMock

from app.db.models import Application, JobPosting, JobState
from app.pipeline.extract import run_extract
from tests.fakes.llm import FakeLLM


def test_run_extract_creates_jobposting_and_advances_state():
    payload = {
        "title": "Dev",
        "company": "Acme",
        "language": "en",
        "description": "build things",
        "requirements": "py",
        "tech_stack": ["python"],
    }
    db = MagicMock()
    app = Application(url="u", url_hash="h" * 64)
    app.id = uuid.uuid4()
    app.user_id = uuid.uuid4()
    app.job_state = JobState.crawling
    text = "x" * 1000

    captured = {}

    def add(obj):
        if isinstance(obj, JobPosting):
            captured["jp"] = obj

    db.add.side_effect = add
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    raw_path = "/tmp/raw.html"

    run_extract(db, app, text, raw_path, llm)

    assert app.job_state == JobState.extracted
    assert app.language == "en"
    assert captured["jp"].title == "Dev"
    assert captured["jp"].application_id == app.id


def test_run_extract_stores_required_documents_and_auto_labels():
    payload = {
        "title": "Backend Engineer",
        "company": "Acme",
        "language": "en",
        "required_documents": ["cv", "cover_letter"],
        "suggested_labels": ["Startup", "Tech"],
    }
    db = MagicMock()
    app = Application(url="u", url_hash="h" * 64)
    app.id = uuid.uuid4()
    app.user_id = uuid.uuid4()
    app.job_state = JobState.crawling
    app.labels = []

    captured = {}

    def add(obj):
        if isinstance(obj, JobPosting):
            captured["jp"] = obj

    db.add.side_effect = add
    db.query.return_value.filter_by.return_value.first.return_value = None
    db.flush = MagicMock()
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))

    run_extract(db, app, "x" * 1000, "/tmp/raw.html", llm)

    assert captured["jp"].required_documents == ["cv", "cover_letter"]
    # Two labels appended to app.labels
    assert len(app.labels) == 2
    label_names = {lbl.name for lbl in app.labels}
    assert label_names == {"Startup", "Tech"}
