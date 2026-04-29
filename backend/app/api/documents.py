import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import AnschreibenVariant, CVVariant, User

router = APIRouter(prefix="/api", tags=["documents"])


class VariantCreate(BaseModel):
    name: str
    source_md: str
    is_default: bool = False


class VariantUpdate(BaseModel):
    name: str | None = None
    source_md: str | None = None
    is_default: bool | None = None


class VariantOut(BaseModel):
    id: uuid.UUID
    name: str
    source_md: str
    is_default: bool

    model_config = {"from_attributes": True}


def _model_for(kind: Literal["cv", "anschreiben"]):
    return CVVariant if kind == "cv" else AnschreibenVariant


def _list(db, user, kind):
    model = _model_for(kind)
    return db.query(model).filter_by(user_id=user.id).order_by(model.created_at.asc()).all()


def _set_default_exclusive(db, user, kind, target_id):
    model = _model_for(kind)
    db.query(model).filter_by(user_id=user.id).update({"is_default": False})
    db.query(model).filter_by(id=target_id, user_id=user.id).update({"is_default": True})


@router.get("/cv-variants", response_model=list[VariantOut])
def list_cv(
    db: Annotated[Session, Depends(db_dep)], user: Annotated[User, Depends(current_user)]
):
    return _list(db, user, "cv")


@router.post("/cv-variants", response_model=VariantOut)
def create_cv(
    body: VariantCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = CVVariant(user_id=user.id, name=body.name, source_md=body.source_md, is_default=False)
    db.add(v)
    db.flush()
    if body.is_default:
        _set_default_exclusive(db, user, "cv", v.id)
    db.commit()
    db.refresh(v)
    return v


@router.patch("/cv-variants/{vid}", response_model=VariantOut)
def update_cv(
    vid: uuid.UUID,
    body: VariantUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(CVVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    if body.name is not None:
        v.name = body.name
    if body.source_md is not None:
        v.source_md = body.source_md
    if body.is_default is not None:
        if body.is_default:
            _set_default_exclusive(db, user, "cv", v.id)
        else:
            v.is_default = False
    db.commit()
    db.refresh(v)
    return v


@router.delete("/cv-variants/{vid}")
def delete_cv(
    vid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(CVVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    db.delete(v)
    db.commit()
    return {"ok": True}


@router.get("/anschreiben-variants", response_model=list[VariantOut])
def list_an(
    db: Annotated[Session, Depends(db_dep)], user: Annotated[User, Depends(current_user)]
):
    return _list(db, user, "anschreiben")


@router.post("/anschreiben-variants", response_model=VariantOut)
def create_an(
    body: VariantCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = AnschreibenVariant(
        user_id=user.id, name=body.name, source_md=body.source_md, is_default=False
    )
    db.add(v)
    db.flush()
    if body.is_default:
        _set_default_exclusive(db, user, "anschreiben", v.id)
    db.commit()
    db.refresh(v)
    return v


@router.patch("/anschreiben-variants/{vid}", response_model=VariantOut)
def update_an(
    vid: uuid.UUID,
    body: VariantUpdate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(AnschreibenVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    if body.name is not None:
        v.name = body.name
    if body.source_md is not None:
        v.source_md = body.source_md
    if body.is_default is not None:
        if body.is_default:
            _set_default_exclusive(db, user, "anschreiben", v.id)
        else:
            v.is_default = False
    db.commit()
    db.refresh(v)
    return v


@router.delete("/anschreiben-variants/{vid}")
def delete_an(
    vid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    v = db.get(AnschreibenVariant, vid)
    if not v or v.user_id != user.id:
        raise HTTPException(404, "not found")
    db.delete(v)
    db.commit()
    return {"ok": True}
