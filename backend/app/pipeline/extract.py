from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models import Application, JobPosting, JobState, Label
from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from app.llm.base import LLMClient

_AUTO_LABEL_COLOR = "#6366f1"


def _upsert_and_assign_labels(db: Session, app: Application, names: list[str]) -> None:
    for name in names:
        label = db.query(Label).filter_by(name=name).first()
        if label is None:
            label = Label(name=name, color=_AUTO_LABEL_COLOR, is_auto=True)
            db.add(label)
            db.flush()
        if label not in app.labels:
            app.labels.append(label)


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
        contact_person=job.contact_person,
        application_email=job.application_email,
        deadline=job.deadline,
        salary=job.salary,
        tech_stack=job.tech_stack,
        seniority=job.seniority,
        work_mode=job.work_mode,
        benefits=job.benefits,
        language=job.language,
        required_documents=job.required_documents or None,
    )
    app.language = job.language
    db.add(jp)
    _upsert_and_assign_labels(db, app, job.suggested_labels)
    app.job_state = JobState.extracted
    db.commit()
