import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

from celery import chain
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep, settings_dep
from app.api.labels import LabelOut
from app.config import Settings, get_settings
from app.db.models import (
    AnschreibenVariant,
    Application,
    ApplicationStatus,
    CVVariant,
    FailedStage,
    JobPosting,
    JobState,
    Label as LabelModel,
    User,
)
from app.pipeline import url_hash
from app.tasks.pipeline import crawl_task, extract_task, generate_task

router = APIRouter(prefix="/api/applications", tags=["applications"])

_BUSY_STATES = {JobState.crawling, JobState.extracting, JobState.generating}


def _reset_for_crawl(db: Session, app_row: Application) -> None:
    if app_row.job_posting:
        db.delete(app_row.job_posting)
    app_row.generated_md = None
    app_row.generated_docx_path = None
    app_row.job_error = None
    app_row.failed_stage = None
    app_row.job_posting_dirty = False
    app_row.job_state = JobState.pending


class CreateApplication(BaseModel):
    url: HttpUrl
    cv_variant_id: uuid.UUID | None = None
    anschreiben_variant_id: uuid.UUID | None = None


class JobPostingOut(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact: dict | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] | None = None
    seniority: str | None = None
    work_mode: str | None = None
    benefits: list[str] | None = None
    language: str | None = None
    required_documents: list[str] | None = None
    mentions_home_office_policy: bool | None = None
    mentions_part_time: bool | None = None

    model_config = {"from_attributes": True}


class JobPostingPatch(BaseModel):
    title: str | None = None
    company: str | None = None
    location: str | None = None
    description: str | None = None
    requirements: str | None = None
    contact: dict | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] | None = None
    seniority: str | None = None
    work_mode: str | None = None
    benefits: list[str] | None = None
    language: str | None = None


class VariantsPatch(BaseModel):
    cv_variant_id: uuid.UUID | None = None
    anschreiben_variant_id: uuid.UUID | None = None
    clear_cv: bool = False
    clear_anschreiben: bool = False


class ApplicationOut(BaseModel):
    id: uuid.UUID
    display_id: int
    url: str
    status: ApplicationStatus
    job_state: JobState
    job_error: str | None
    failed_stage: FailedStage | None
    language: str | None
    generated_md: str | None
    has_docx: bool
    cv_variant_id: uuid.UUID | None
    anschreiben_variant_id: uuid.UUID | None
    job_posting_dirty: bool
    posting_online: bool | None
    labels: list[LabelOut]
    job_posting: JobPostingOut | None
    inquiry_subject: str | None
    inquiry_body: str | None
    inquiry_sent_at: datetime | None

    @classmethod
    def from_orm_row(cls, app: Application) -> "ApplicationOut":
        return cls(
            id=app.id,
            display_id=app.display_id,
            url=app.url,
            status=app.status,
            job_state=app.job_state,
            job_error=app.job_error,
            failed_stage=app.failed_stage,
            language=app.language,
            generated_md=app.generated_md,
            has_docx=app.generated_docx_path is not None,
            cv_variant_id=app.cv_variant_id,
            anschreiben_variant_id=app.anschreiben_variant_id,
            job_posting_dirty=app.job_posting_dirty,
            posting_online=app.posting_online,
            labels=[LabelOut.model_validate(lbl) for lbl in app.labels],
            job_posting=(
                JobPostingOut.model_validate(app.job_posting) if app.job_posting else None
            ),
            inquiry_subject=app.inquiry_subject,
            inquiry_body=app.inquiry_body,
            inquiry_sent_at=app.inquiry_sent_at,
        )


def _check_variant_ownership(
    db: Session, variant_id: uuid.UUID | None, model, user: User, label: str
) -> uuid.UUID | None:
    if variant_id is None:
        return None
    row = db.query(model).filter_by(id=variant_id, user_id=user.id).first()
    if row is None:
        raise HTTPException(400, f"{label} not found or does not belong to current user")
    return row.id


def _start_crawl_chain(app_id: uuid.UUID) -> None:
    chain(crawl_task.s(str(app_id)), extract_task.s()).apply_async()


def _start_generate(app_id: uuid.UUID) -> None:
    generate_task.apply_async(args=[str(app_id)])


def _load_owned(db: Session, aid: uuid.UUID, user: User) -> Application:
    app = db.get(Application, aid)
    if not app or app.user_id != user.id or app.deleted_at is not None:
        raise HTTPException(404, "not found")
    return app


@router.post("", response_model=ApplicationOut, status_code=202)
def create(
    body: CreateApplication,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    cv_id = _check_variant_ownership(db, body.cv_variant_id, CVVariant, user, "cv_variant_id")
    an_id = _check_variant_ownership(
        db, body.anschreiben_variant_id, AnschreibenVariant, user, "anschreiben_variant_id"
    )
    h = url_hash(str(body.url))
    existing = db.query(Application).filter_by(user_id=user.id, url_hash=h).first()
    if existing:
        raise HTTPException(409, f"application already exists: {existing.id}")
    app_row = Application(
        user_id=user.id,
        url=str(body.url),
        url_hash=h,
        cv_variant_id=cv_id,
        anschreiben_variant_id=an_id,
    )
    db.add(app_row)
    db.commit()
    db.refresh(app_row)
    _start_crawl_chain(app_row.id)
    return ApplicationOut.from_orm_row(app_row)


@router.get("", response_model=list[ApplicationOut])
def list_apps(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    label_ids: list[uuid.UUID] | None = Query(default=None),
):
    q = db.query(Application).filter(
        Application.user_id == user.id,
        Application.deleted_at.is_(None),
    )
    if label_ids:
        q = q.filter(Application.labels.any(LabelModel.id.in_(label_ids)))
    rows = q.order_by(Application.created_at.desc()).all()
    return [ApplicationOut.from_orm_row(r) for r in rows]


@router.get("/{aid}", response_model=ApplicationOut)
def get_app(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    return ApplicationOut.from_orm_row(_load_owned(db, aid, user))


class StatusUpdate(BaseModel):
    status: ApplicationStatus


@router.patch("/{aid}", response_model=ApplicationOut)
def update_status(
    aid: uuid.UUID,
    body: StatusUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    app_row.status = body.status
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.delete("/{aid}", status_code=204)
def delete_application(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    if app_row.deleted_at is None:
        app_row.deleted_at = datetime.now(timezone.utc)
        db.commit()
    return None


@router.patch("/{aid}/job-posting", response_model=ApplicationOut)
def patch_job_posting(
    aid: uuid.UUID,
    body: JobPostingPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_state in {JobState.crawling, JobState.extracting, JobState.generating}:
        raise HTTPException(409, "pipeline running")
    if app_row.job_posting is None:
        raise HTTPException(404, "no job posting yet")
    updates = body.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(app_row.job_posting, k, v)
    if app_row.generated_md is not None and updates:
        app_row.job_posting_dirty = True
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.patch("/{aid}/variants", response_model=ApplicationOut)
def patch_variants(
    aid: uuid.UUID,
    body: VariantsPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_state == JobState.generating:
        raise HTTPException(409, "generation running")
    if body.cv_variant_id is not None:
        app_row.cv_variant_id = _check_variant_ownership(
            db, body.cv_variant_id, CVVariant, user, "cv_variant_id"
        )
    elif body.clear_cv:
        app_row.cv_variant_id = None
    if body.anschreiben_variant_id is not None:
        app_row.anschreiben_variant_id = _check_variant_ownership(
            db, body.anschreiben_variant_id, AnschreibenVariant, user, "anschreiben_variant_id"
        )
    elif body.clear_anschreiben:
        app_row.anschreiben_variant_id = None
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.post("/{aid}/generate", response_model=ApplicationOut, status_code=202)
def generate_endpoint(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if not app_row.cv_variant_id or not app_row.anschreiben_variant_id:
        raise HTTPException(400, "cv_variant_id and anschreiben_variant_id required")
    if app_row.job_posting is None:
        raise HTTPException(400, "no job posting yet — run extraction first")
    allowed = {JobState.extracted, JobState.ready}
    if app_row.job_state == JobState.failed:
        if app_row.failed_stage != FailedStage.generate:
            raise HTTPException(409, "earlier stage failed — use /retry")
    elif app_row.job_state not in allowed:
        raise HTTPException(409, "pipeline busy")
    app_row.failed_stage = None
    app_row.job_error = None
    app_row.job_state = JobState.generating
    db.commit()
    db.refresh(app_row)
    _start_generate(app_row.id)
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.post("/{aid}/retry", response_model=ApplicationOut)
def retry(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_state in _BUSY_STATES:
        raise HTTPException(409, "pipeline already running")

    failed_stage = app_row.failed_stage
    if app_row.job_state in (JobState.ready, JobState.extracted) or failed_stage in (
        FailedStage.crawl,
        FailedStage.extract,
        None,
    ):
        # extract_task needs the crawl payload, which isn't persisted —
        # rerun the full crawl→extract chain.
        _reset_for_crawl(db, app_row)
        db.commit()
        db.refresh(app_row)
        _start_crawl_chain(app_row.id)
        return ApplicationOut.from_orm_row(app_row)

    # failed_stage == generate
    if not app_row.cv_variant_id or not app_row.anschreiben_variant_id:
        raise HTTPException(400, "cannot retry generate without variants")
    app_row.job_error = None
    app_row.failed_stage = None
    app_row.job_state = JobState.generating
    db.commit()
    db.refresh(app_row)
    _start_generate(app_row.id)
    return ApplicationOut.from_orm_row(app_row)


@router.get("/{aid}/docx")
def download_docx(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if not app_row.generated_docx_path or not Path(app_row.generated_docx_path).exists():
        raise HTTPException(404, "docx not ready")
    return FileResponse(
        app_row.generated_docx_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename="anschreiben.docx",
    )


@router.post("/{aid}/labels/{label_id}", response_model=ApplicationOut)
def assign_label(
    aid: uuid.UUID,
    label_id: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    label = db.get(LabelModel, label_id)
    if label is None:
        raise HTTPException(404, "label not found")
    if label not in app_row.labels:
        app_row.labels.append(label)
        db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.delete("/{aid}/labels/{label_id}", response_model=ApplicationOut)
def remove_label(
    aid: uuid.UUID,
    label_id: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    label = db.get(LabelModel, label_id)
    if label and label in app_row.labels:
        app_row.labels.remove(label)
        db.commit()
        db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


# ---------------------------------------------------------------------------
# Inquiry endpoints
# ---------------------------------------------------------------------------

def _inquiry_llm():
    from app.llm.groq import GroqClient
    s = get_settings()
    return GroqClient(api_key=s.llm_api_key, model=s.llm_model, base_url=s.llm_base_url)


class InquiryPatch(BaseModel):
    subject: str
    body: str


class InquiryDraftOut(BaseModel):
    subject: str
    body: str
    recipient: str | None
    sent_at: datetime | None = None


class InquiryMarkSentOut(BaseModel):
    sent_at: datetime


def _build_inquiry_job(app_row: Application):
    from app.extractor.schemas import ExtractedJobPosting
    jp = app_row.job_posting
    return ExtractedJobPosting(
        title=jp.title,
        company=jp.company,
        location=jp.location,
        language=jp.language or "de",
    )


def _ensure_inquiry_prompt(db: Session, user: User) -> str:
    from app.db.models import InquiryPromptTemplate
    from app.inquiry.prompts import DEFAULT_TEMPLATE
    row = db.query(InquiryPromptTemplate).filter_by(user_id=user.id).first()
    if row is None:
        row = InquiryPromptTemplate(user_id=user.id, source_md=DEFAULT_TEMPLATE)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row.source_md


@router.post("/{aid}/inquiry/draft", response_model=InquiryDraftOut)
def draft_inquiry(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    if app_row.job_posting is None:
        raise HTTPException(400, "no job posting yet")
    ask_ho = not bool(app_row.job_posting.mentions_home_office_policy)
    ask_pt = not bool(app_row.job_posting.mentions_part_time)
    if not ask_ho and not ask_pt:
        raise HTTPException(400, "Posting covers both topics.")
    system_md = _ensure_inquiry_prompt(db, user)
    from app.inquiry import draft as inquiry_draft
    try:
        email = inquiry_draft(
            job=_build_inquiry_job(app_row),
            language=app_row.job_posting.language or app_row.language or "de",
            ask_home_office=ask_ho,
            ask_part_time=ask_pt,
            system_md=system_md,
            llm=_inquiry_llm(),
        )
    except Exception as exc:
        raise HTTPException(502, f"draft failed: {exc}") from exc
    app_row.inquiry_subject = email.subject
    app_row.inquiry_body = email.body
    db.commit()
    db.refresh(app_row)
    jp = app_row.job_posting
    recipient = getattr(jp, "application_email", None)
    return InquiryDraftOut(
        subject=email.subject,
        body=email.body,
        recipient=recipient,
        sent_at=app_row.inquiry_sent_at,
    )


@router.patch("/{aid}/inquiry", response_model=InquiryDraftOut)
def patch_inquiry(
    aid: uuid.UUID,
    body: InquiryPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    app_row.inquiry_subject = body.subject
    app_row.inquiry_body = body.body
    db.commit()
    db.refresh(app_row)
    jp = app_row.job_posting
    recipient = getattr(jp, "application_email", None)
    return InquiryDraftOut(
        subject=app_row.inquiry_subject or "",
        body=app_row.inquiry_body or "",
        recipient=recipient,
        sent_at=app_row.inquiry_sent_at,
    )


@router.post("/{aid}/inquiry/mark-sent", response_model=InquiryMarkSentOut)
def mark_inquiry_sent(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = _load_owned(db, aid, user)
    app_row.inquiry_sent_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(app_row)
    return InquiryMarkSentOut(sent_at=app_row.inquiry_sent_at)
