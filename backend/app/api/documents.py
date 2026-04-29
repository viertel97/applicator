import uuid
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import AnschreibenVariant, CVVariant, User
from app.renderer.from_docx import docx_bytes_to_markdown

router = APIRouter(prefix="/api", tags=["documents"])

MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB


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


def _has_any(db, user, kind) -> bool:
    model = _model_for(kind)
    return db.query(model.id).filter_by(user_id=user.id).first() is not None


async def _read_docx_upload(file: UploadFile) -> str:
    if not (file.filename or "").lower().endswith(".docx"):
        raise HTTPException(400, "only .docx files are accepted")
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "file too large")
    try:
        return docx_bytes_to_markdown(data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"failed to parse docx: {exc}") from exc


def _upload_variant(db: Session, user: User, kind, file_name: str, source_md: str):
    model = _model_for(kind)
    name = Path(file_name or "uploaded.docx").stem or "uploaded"
    is_first = not _has_any(db, user, kind)
    v = model(user_id=user.id, name=name, source_md=source_md, is_default=False)
    db.add(v)
    db.flush()
    if is_first:
        _set_default_exclusive(db, user, kind, v.id)
    db.commit()
    db.refresh(v)
    return v


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


@router.post("/cv-variants/upload", response_model=VariantOut)
async def upload_cv(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
):
    source_md = await _read_docx_upload(file)
    return _upload_variant(db, user, "cv", file.filename or "", source_md)


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


@router.post("/anschreiben-variants/upload", response_model=VariantOut)
async def upload_an(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    file: Annotated[UploadFile, File()],
):
    source_md = await _read_docx_upload(file)
    return _upload_variant(db, user, "anschreiben", file.filename or "", source_md)


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
