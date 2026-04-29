import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import current_user, db_dep, settings_dep
from app.config import Settings
from app.db.models import (
    AnschreibenVariant,
    Application,
    ApplicationStatus,
    CVVariant,
    JobState,
    User,
)
from app.db.session import get_engine
from app.llm.groq import GroqClient
from app.pipeline import Pipeline, url_hash

router = APIRouter(prefix="/api/applications", tags=["applications"])


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
    contact_person: str | None = None
    application_email: str | None = None
    deadline: str | None = None
    salary: str | None = None
    tech_stack: list[str] | None = None
    seniority: str | None = None
    work_mode: str | None = None
    benefits: list[str] | None = None
    language: str | None = None

    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: uuid.UUID
    url: str
    status: ApplicationStatus
    job_state: JobState
    job_error: str | None
    language: str | None
    generated_md: str | None
    has_docx: bool
    job_posting: JobPostingOut | None

    @classmethod
    def from_orm_row(cls, app: Application) -> "ApplicationOut":
        return cls(
            id=app.id,
            url=app.url,
            status=app.status,
            job_state=app.job_state,
            job_error=app.job_error,
            language=app.language,
            generated_md=app.generated_md,
            has_docx=app.generated_docx_path is not None,
            job_posting=(
                JobPostingOut.model_validate(app.job_posting) if app.job_posting else None
            ),
        )


def _llm(settings: Settings) -> GroqClient:
    return GroqClient(
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        base_url=settings.llm_base_url,
    )


def _kickoff(
    background_tasks: BackgroundTasks, application_id: uuid.UUID, settings: Settings
) -> None:
    factory = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)

    @contextmanager
    def db_factory():
        s = factory()
        try:
            yield s
        finally:
            s.close()

    pipeline = Pipeline(db_factory=db_factory, llm=_llm(settings), settings=settings)
    background_tasks.add_task(pipeline.run, application_id)


def _default_id(db: Session, user: User, model) -> uuid.UUID | None:
    row = db.query(model).filter_by(user_id=user.id, is_default=True).first()
    return row.id if row else None


@router.post("", response_model=ApplicationOut, status_code=202)
def create(
    body: CreateApplication,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    cv_id = body.cv_variant_id or _default_id(db, user, CVVariant)
    an_id = body.anschreiben_variant_id or _default_id(db, user, AnschreibenVariant)
    if not cv_id or not an_id:
        raise HTTPException(400, "no default CV or Anschreiben configured")
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
    _kickoff(background_tasks, app_row.id, settings)
    return ApplicationOut.from_orm_row(app_row)


@router.get("", response_model=list[ApplicationOut])
def list_apps(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    rows = (
        db.query(Application)
        .filter_by(user_id=user.id)
        .order_by(Application.created_at.desc())
        .all()
    )
    return [ApplicationOut.from_orm_row(r) for r in rows]


@router.get("/{aid}", response_model=ApplicationOut)
def get_app(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    return ApplicationOut.from_orm_row(app_row)


class StatusUpdate(BaseModel):
    status: ApplicationStatus


@router.patch("/{aid}", response_model=ApplicationOut)
def update_status(
    aid: uuid.UUID,
    body: StatusUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    app_row.status = body.status
    db.commit()
    db.refresh(app_row)
    return ApplicationOut.from_orm_row(app_row)


@router.post("/{aid}/retry", response_model=ApplicationOut)
def retry(
    aid: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    settings: Annotated[Settings, Depends(settings_dep)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    if app_row.job_state not in (JobState.ready, JobState.failed):
        raise HTTPException(409, "pipeline already running")
    if app_row.job_posting:
        db.delete(app_row.job_posting)
    app_row.generated_md = None
    app_row.generated_docx_path = None
    app_row.job_error = None
    app_row.job_state = JobState.pending
    db.commit()
    db.refresh(app_row)
    _kickoff(background_tasks, app_row.id, settings)
    return ApplicationOut.from_orm_row(app_row)


@router.get("/{aid}/docx")
def download_docx(
    aid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    app_row = db.get(Application, aid)
    if not app_row or app_row.user_id != user.id:
        raise HTTPException(404, "not found")
    if not app_row.generated_docx_path or not Path(app_row.generated_docx_path).exists():
        raise HTTPException(404, "docx not ready")
    return FileResponse(
        app_row.generated_docx_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename="anschreiben.docx",
    )
