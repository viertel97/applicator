import re
import unicodedata
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import current_user, db_dep
from app.db.models import Application, DiscardReason, User

router = APIRouter(prefix="/api/discard-reasons", tags=["discard-reasons"])

SYSTEM_REASONS: list[tuple[str, str, int]] = [
    ("no_reply", "No reply", 10),
    ("rejected", "Rejected", 20),
    ("withdrew_self", "Withdrew myself", 30),
    ("location", "Location mismatch", 40),
    ("salary", "Salary mismatch", 50),
    ("tech_mismatch", "Tech mismatch", 60),
    ("seniority", "Seniority mismatch", 70),
    ("posting_offline", "Posting offline", 80),
    ("duplicate", "Duplicate", 90),
    ("other", "Other", 100),
]


def _derive_slug(label: str) -> str:
    norm = unicodedata.normalize("NFKD", label.strip().lower())
    ascii_only = norm.encode("ascii", "ignore").decode()
    underscored = re.sub(r"[^a-z0-9]+", "_", ascii_only).strip("_")
    return (underscored or "reason")[:64]


def _unique_slug(base: str, taken: set[str]) -> str:
    if base not in taken:
        return base
    i = 2
    while True:
        suffix = f"_{i}"
        candidate = base[: 64 - len(suffix)] + suffix
        if candidate not in taken:
            return candidate
        i += 1


def seed_system_reasons(db: Session, user_id: uuid.UUID) -> None:
    """Idempotently insert any missing system reasons for the user.

    Does NOT commit — the caller is responsible for committing.
    """
    existing = {
        r.slug
        for r in db.query(DiscardReason).filter_by(user_id=user_id).all()
    }
    for slug, label, sort in SYSTEM_REASONS:
        if slug in existing:
            continue
        db.add(
            DiscardReason(
                user_id=user_id,
                slug=slug,
                label=label,
                is_system=True,
                sort_order=sort,
            )
        )


class ReasonOut(BaseModel):
    id: uuid.UUID
    slug: str
    label: str
    is_system: bool
    is_archived: bool
    sort_order: int
    usage_count: int

    model_config = {"from_attributes": True}


class ReasonCreate(BaseModel):
    label: str
    slug: str | None = None


class ReasonPatch(BaseModel):
    label: str | None = None
    is_archived: bool | None = None
    sort_order: int | None = None


def _to_out(db: Session, r: DiscardReason) -> ReasonOut:
    cnt = (
        db.query(func.count(Application.id))
        .filter(Application.discard_reason_id == r.id)
        .scalar()
        or 0
    )
    return ReasonOut(
        id=r.id,
        slug=r.slug,
        label=r.label,
        is_system=r.is_system,
        is_archived=r.is_archived,
        sort_order=r.sort_order,
        usage_count=cnt,
    )


@router.get("", response_model=list[ReasonOut])
def list_reasons(
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
    include_archived: int = Query(0),
):
    if db.query(DiscardReason).filter_by(user_id=user.id).count() == 0:
        seed_system_reasons(db, user.id)
        try:
            db.commit()
        except IntegrityError:
            # concurrent first-call from another request already seeded; ignore
            db.rollback()
    q = db.query(DiscardReason).filter_by(user_id=user.id)
    if not include_archived:
        q = q.filter_by(is_archived=False)
    rows = q.order_by(DiscardReason.sort_order, DiscardReason.label).all()
    return [_to_out(db, r) for r in rows]


@router.post("", response_model=ReasonOut)
def create_reason(
    body: ReasonCreate,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    if not body.label.strip():
        raise HTTPException(400, "label required")
    base = _derive_slug(body.slug) if body.slug else _derive_slug(body.label)
    taken = {
        r.slug
        for r in db.query(DiscardReason).filter_by(user_id=user.id).all()
    }
    slug = _unique_slug(base, taken)
    max_sort = (
        db.query(func.coalesce(func.max(DiscardReason.sort_order), 0))
        .filter_by(user_id=user.id)
        .scalar()
        or 0
    )
    r = DiscardReason(
        user_id=user.id,
        slug=slug,
        label=body.label.strip(),
        is_system=False,
        sort_order=max_sort + 10,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return _to_out(db, r)


@router.patch("/{rid}", response_model=ReasonOut)
def patch_reason(
    rid: uuid.UUID,
    body: ReasonPatch,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    r = db.get(DiscardReason, rid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "not found")
    if body.label is not None:
        stripped = body.label.strip()
        if not stripped:
            raise HTTPException(400, "label must be non-empty")
        r.label = stripped
    if body.is_archived is not None:
        r.is_archived = body.is_archived
    if body.sort_order is not None:
        r.sort_order = body.sort_order
    db.commit()
    db.refresh(r)
    return _to_out(db, r)


@router.delete("/{rid}", status_code=204)
def delete_reason(
    rid: uuid.UUID,
    db: Annotated[Session, Depends(db_dep)],
    user: Annotated[User, Depends(current_user)],
):
    r = db.get(DiscardReason, rid)
    if not r or r.user_id != user.id:
        raise HTTPException(404, "not found")
    in_use = (
        db.query(func.count(Application.id))
        .filter(Application.discard_reason_id == r.id)
        .scalar()
    )
    if in_use:
        raise HTTPException(409, "reason in use — archive instead")
    db.delete(r)
    db.commit()
    return None
