from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import (
    AnschreibenVariant,
    Application,
    CVVariant,
    JobState,
)
from app.extractor.schemas import ExtractedJobPosting
from app.generator import generate
from app.llm.base import LLMClient
from app.renderer.docx import to_docx


def run_generate(
    db: Session,
    app: Application,
    llm: LLMClient,
    settings: Settings,
) -> None:
    if app.cv_variant_id is None or app.anschreiben_variant_id is None:
        raise RuntimeError("cv_variant_id and anschreiben_variant_id required")
    if app.job_posting is None:
        raise RuntimeError("job_posting missing — run extract first")
    cv = db.get(CVVariant, app.cv_variant_id)
    an = db.get(AnschreibenVariant, app.anschreiben_variant_id)
    if cv is None or an is None:
        raise RuntimeError("variant not found")

    app.job_state = JobState.generating
    db.commit()

    jp = app.job_posting
    job = ExtractedJobPosting(
        title=jp.title,
        company=jp.company,
        location=jp.location,
        description=jp.description,
        requirements=jp.requirements,
        contact_person=jp.contact_person,
        application_email=jp.application_email,
        deadline=jp.deadline,
        salary=jp.salary,
        tech_stack=jp.tech_stack or [],
        seniority=jp.seniority,
        work_mode=jp.work_mode,
        benefits=jp.benefits or [],
        language=jp.language,
    )
    md = generate(job, cv.source_md, an.source_md, jp.language, llm)
    app.generated_md = md

    docx_path = (
        Path(settings.data_dir)
        / str(app.user_id)
        / str(app.id)
        / "anschreiben.docx"
    )
    to_docx(md, docx_path)
    app.generated_docx_path = str(docx_path)

    app.job_state = JobState.ready
    app.job_posting_dirty = False
    app.failed_stage = None
    app.job_error = None
    db.commit()
