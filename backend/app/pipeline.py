import hashlib
import uuid
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.crawler.fetcher import HybridFetcher
from app.crawler.httpx_fetcher import FetchResult
from app.db.models import AnschreibenVariant, Application, CVVariant, JobPosting, JobState
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.generator import generate
from app.llm.base import LLMClient
from app.renderer.docx import to_docx


def url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


class Pipeline:
    def __init__(
        self,
        db_factory: Callable[[], Session],
        llm: LLMClient,
        settings: Settings,
        fetcher=None,
    ):
        self.db_factory = db_factory
        self.llm = llm
        self.settings = settings
        self.fetcher = fetcher or HybridFetcher()

    def run(self, application_id: uuid.UUID) -> None:
        with self.db_factory() as db:
            app = db.get(Application, application_id)
            if app is None:
                return
            try:
                self._run_steps(db, app)
            except Exception as e:  # noqa: BLE001
                db.rollback()
                app2 = db.get(Application, application_id)
                if app2:
                    app2.job_state = JobState.failed
                    app2.job_error = str(e)[:1000]
                    db.commit()

    def _run_steps(self, db: Session, app: Application) -> None:
        app.job_state = JobState.crawling
        db.commit()
        result = self.fetcher.fetch(app.url)
        raw_path = self._save_raw(app, result)

        app.job_state = JobState.extracting
        db.commit()
        job: ExtractedJobPosting = extract(result.text, self.llm)
        jp = JobPosting(
            application_id=app.id,
            raw_text=result.text[:200000],
            raw_html_path=str(raw_path),
            title=job.title,
            company=job.company,
            location=job.location,
            description=job.description,
            requirements=job.requirements,
            contact_person=job.contact_person,
            application_email=job.application_email,
            deadline=job.deadline,
            salary=job.salary,
            tech_stack=job.tech_stack,
            seniority=job.seniority,
            work_mode=job.work_mode,
            benefits=job.benefits,
            language=job.language,
        )
        app.language = job.language
        db.add(jp)
        db.commit()

        app.job_state = JobState.generating
        db.commit()
        cv = db.get(CVVariant, app.cv_variant_id)
        an = db.get(AnschreibenVariant, app.anschreiben_variant_id)
        if cv is None or an is None:
            raise RuntimeError(
                f"CV variant {app.cv_variant_id} or Anschreiben variant "
                f"{app.anschreiben_variant_id} not found"
            )
        md = generate(job, cv.source_md, an.source_md, job.language, self.llm)
        app.generated_md = md

        docx_path = (
            Path(self.settings.data_dir)
            / str(app.user_id)
            / str(app.id)
            / "anschreiben.docx"
        )
        to_docx(md, docx_path)
        app.generated_docx_path = str(docx_path)

        app.job_state = JobState.ready
        app.job_error = None
        db.commit()

    def _save_raw(self, app: Application, result: FetchResult) -> Path:
        raw_path = (
            Path(self.settings.data_dir)
            / str(app.user_id)
            / str(app.id)
            / "raw.html"
        )
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(result.html, encoding="utf-8")
        return raw_path
