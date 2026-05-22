from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import InquiryPromptTemplate, User
from app.inquiry.prompts import DEFAULT_TEMPLATE

router = APIRouter(prefix="/api/settings/inquiry-prompt", tags=["inquiry-prompt"])


class InquiryPromptOut(BaseModel):
    source_md: str


class InquiryPromptPut(BaseModel):
    source_md: str


def _get_or_seed(db: Session, user: User) -> InquiryPromptTemplate:
    row = db.query(InquiryPromptTemplate).filter_by(user_id=user.id).first()
    if row is None:
        row = InquiryPromptTemplate(user_id=user.id, source_md=DEFAULT_TEMPLATE)
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("", response_model=InquiryPromptOut)
def get_prompt(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    row = _get_or_seed(db, user)
    return InquiryPromptOut(source_md=row.source_md)


@router.put("", response_model=InquiryPromptOut)
def put_prompt(
    body: InquiryPromptPut,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    row = _get_or_seed(db, user)
    row.source_md = body.source_md
    db.commit()
    db.refresh(row)
    return InquiryPromptOut(source_md=row.source_md)
