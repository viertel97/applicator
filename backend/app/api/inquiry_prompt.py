from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import InquiryPromptTemplate, User
from app.inquiry.prompts import DEFAULT_TEMPLATE
from app.inquiry.preview import build_preview

router = APIRouter(prefix="/api/settings/inquiry-prompt", tags=["inquiry-prompt"])


class InquiryPromptOut(BaseModel):
    source_md: str
    user_prompt_md: str | None = None
    question_home_office_de: str | None = None
    question_home_office_en: str | None = None
    question_part_time_de: str | None = None
    question_part_time_en: str | None = None
    body_template_de: str | None = None
    body_template_en: str | None = None


class InquiryPromptPut(BaseModel):
    source_md: str
    user_prompt_md: str | None = None
    question_home_office_de: str | None = None
    question_home_office_en: str | None = None
    question_part_time_de: str | None = None
    question_part_time_en: str | None = None
    body_template_de: str | None = None
    body_template_en: str | None = None


class InquiryPreviewLang(BaseModel):
    system_prompt: str
    user_prompt: str
    subject: str
    greeting: str
    questions: list[str]
    email: str


class InquiryPreviewOut(BaseModel):
    de: InquiryPreviewLang
    en: InquiryPreviewLang


_OLD_TEMPLATE_PREFIXES = ("Du hilfst dem Bewerber", "Du schreibst eine kurze Offene Fragen-Mail")


def _get_or_seed(db: Session, user: User) -> InquiryPromptTemplate:
    row = db.query(InquiryPromptTemplate).filter_by(user_id=user.id).first()
    if row is None:
        row = InquiryPromptTemplate(user_id=user.id, source_md=DEFAULT_TEMPLATE)
        db.add(row)
        db.commit()
        db.refresh(row)
    elif any(row.source_md.startswith(p) for p in _OLD_TEMPLATE_PREFIXES):
        row.source_md = DEFAULT_TEMPLATE
        db.commit()
        db.refresh(row)
    return row


def _row_to_out(row: InquiryPromptTemplate) -> InquiryPromptOut:
    return InquiryPromptOut(
        source_md=row.source_md,
        user_prompt_md=row.user_prompt_md,
        question_home_office_de=row.question_home_office_de,
        question_home_office_en=row.question_home_office_en,
        question_part_time_de=row.question_part_time_de,
        question_part_time_en=row.question_part_time_en,
        body_template_de=row.body_template_de,
        body_template_en=row.body_template_en,
    )


@router.get("", response_model=InquiryPromptOut)
def get_prompt(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    return _row_to_out(_get_or_seed(db, user))


@router.put("", response_model=InquiryPromptOut)
def put_prompt(
    body: InquiryPromptPut,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    row = _get_or_seed(db, user)
    row.source_md = body.source_md
    row.user_prompt_md = body.user_prompt_md or None
    row.question_home_office_de = body.question_home_office_de or None
    row.question_home_office_en = body.question_home_office_en or None
    row.question_part_time_de = body.question_part_time_de or None
    row.question_part_time_en = body.question_part_time_en or None
    row.body_template_de = body.body_template_de or None
    row.body_template_en = body.body_template_en or None
    db.commit()
    db.refresh(row)
    return _row_to_out(row)


@router.post("/preview", response_model=InquiryPreviewOut)
def preview_prompt(
    body: InquiryPromptPut,
    user: Annotated[User, Depends(current_user)],
):
    return build_preview(**body.model_dump())
