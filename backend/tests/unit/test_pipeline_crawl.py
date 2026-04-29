from pathlib import Path
from unittest.mock import MagicMock

from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobState
from app.pipeline.crawl import run_crawl
from tests.fakes.fetcher import FakeFetcher


def test_run_crawl_writes_raw_html_and_sets_state(tmp_path):
    fetcher = FakeFetcher(
        result=FetchResult(url="u", status_code=200, html="<html>hi</html>", text="hi")
    )
    settings = MagicMock(data_dir=str(tmp_path))
    db = MagicMock()
    app = Application(url="https://x.test/j", url_hash="h" * 64)
    app.id = __import__("uuid").uuid4()
    app.user_id = __import__("uuid").uuid4()
    app.job_state = JobState.pending

    raw_path, fetch_result = run_crawl(db, app, fetcher, settings)

    assert Path(raw_path).read_text() == "<html>hi</html>"
    assert fetch_result.text == "hi"
    assert app.job_state == JobState.crawling
    db.commit.assert_called()
