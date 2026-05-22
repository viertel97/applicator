from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting, JobState
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.labels.upsert import upsert_and_assign_labels
from app.llm.base import LLMClient


def run_extract(
    db: Session,
    app: Application,
    text: str,
    raw_path: Path | str,
    llm: LLMClient,
) -> None:
    app.job_state = JobState.extracting
    db.commit()
    if app.job_posting is not None:
        db.delete(app.job_posting)
        db.flush()
    job: ExtractedJobPosting = extract(text, llm)
    jp = JobPosting(
        application_id=app.id,
        raw_text=text[:200000],
        raw_html_path=str(raw_path),
        title=job.title,
        company=job.company,
        location=job.location,
        description=job.description,
        requirements=job.requirements,
        contact=job.contact.model_dump() if job.contact else None,
        deadline=job.deadline,
        salary=job.salary,
        tech_stack=job.tech_stack,
        seniority=job.seniority,
        work_mode=job.work_mode,
        benefits=job.benefits,
        language=job.language,
        required_documents=job.required_documents,
        mentions_home_office_policy=job.mentions_home_office_policy,
        mentions_part_time=job.mentions_part_time,
    )
    app.language = job.language
    db.add(jp)
    upsert_and_assign_labels(db, app, job.suggested_labels)
    app.job_state = JobState.extracted
    db.commit()
