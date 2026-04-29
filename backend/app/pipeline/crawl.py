from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.crawler.fetcher import HybridFetcher
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobState


def run_crawl(
    db: Session,
    app: Application,
    fetcher: HybridFetcher,
    settings: Settings,
) -> tuple[Path, FetchResult]:
    app.job_state = JobState.crawling
    db.commit()
    result = fetcher.fetch(app.url)
    raw_path = (
        Path(settings.data_dir)
        / str(app.user_id)
        / str(app.id)
        / "raw.html"
    )
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(result.html, encoding="utf-8")
    return raw_path, result
