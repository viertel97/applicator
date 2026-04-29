import json
import uuid
from unittest.mock import MagicMock

from app.crawler.httpx_fetcher import FetchResult
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
    fetch_result = FetchResult(url="u", status_code=200, html="<p>x</p>", text="x" * 1000)

    captured = {}

    def add(obj):
        if isinstance(obj, JobPosting):
            captured["jp"] = obj

    db.add.side_effect = add
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    raw_path = "/tmp/raw.html"

    run_extract(db, app, fetch_result, raw_path, llm)

    assert app.job_state == JobState.extracted
    assert app.language == "en"
    assert captured["jp"].title == "Dev"
    assert captured["jp"].application_id == app.id
