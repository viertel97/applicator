from pathlib import Path

from sqlalchemy.orm import Session

from app.crawler.httpx_fetcher import FetchResult
from app.db.models import Application, JobPosting, JobState
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.llm.base import LLMClient


def run_extract(
    db: Session,
    app: Application,
    fetch_result: FetchResult,
    raw_path: Path | str,
    llm: LLMClient,
) -> None:
    app.job_state = JobState.extracting
    db.commit()
    if app.job_posting is not None:
        db.delete(app.job_posting)
        db.flush()
    job: ExtractedJobPosting = extract(fetch_result.text, llm)
    jp = JobPosting(
        application_id=app.id,
        raw_text=fetch_result.text[:200000],
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
    app.job_state = JobState.extracted
    db.commit()
