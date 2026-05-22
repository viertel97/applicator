import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import cast, String
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Label, LabelCategory, User

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    name: str
    color: str
    category: LabelCategory


class LabelPatch(BaseModel):
    name: str | None = None
    color: str | None = None
    category: LabelCategory | None = None


class LabelOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    is_auto: bool
    category: LabelCategory

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LabelOut])
def list_labels(
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    return (
        db.query(Label)
        .order_by(cast(Label.category, String), Label.name)
        .all()
    )


@router.post("", response_model=LabelOut, status_code=201)
def create_label(
    body: LabelCreate,
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    if db.query(Label).filter_by(name=body.name).first():
        raise HTTPException(409, "label already exists")
    label = Label(
        name=body.name,
        color=body.color,
        is_auto=False,
        category=body.category,
    )
    db.add(label)
    db.commit()
    db.refresh(label)
    return label


@router.patch("/{label_id}", response_model=LabelOut)
def patch_label(
    label_id: uuid.UUID,
    body: LabelPatch,
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    label = db.get(Label, label_id)
    if label is None:
        raise HTTPException(404, "not found")
    if body.name is not None:
        label.name = body.name
    if body.color is not None:
        label.color = body.color
    if body.category is not None:
        label.category = body.category
    db.commit()
    db.refresh(label)
    return label
