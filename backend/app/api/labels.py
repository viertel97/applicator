import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Label, User

router = APIRouter(prefix="/api/labels", tags=["labels"])


class LabelCreate(BaseModel):
    name: str
    color: str


class LabelOut(BaseModel):
    id: uuid.UUID
    name: str
    color: str
    is_auto: bool

    model_config = {"from_attributes": True}


@router.get("", response_model=list[LabelOut])
def list_labels(
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    return db.query(Label).order_by(Label.name).all()


@router.post("", response_model=LabelOut, status_code=201)
def create_label(
    body: LabelCreate,
    db: Annotated[Session, Depends(db_dep)],
    _user: Annotated[User, Depends(current_user)],
):
    if db.query(Label).filter_by(name=body.name).first():
        raise HTTPException(409, "label already exists")
    label = Label(name=body.name, color=body.color, is_auto=False)
    db.add(label)
    db.commit()
    db.refresh(label)
    return label
