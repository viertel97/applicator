from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Sequence as SASequence,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ApplicationStatus(str, enum.Enum):
    draft = "draft"
    applied = "applied"
    offer = "offer"
    rejected = "rejected"
    accepted = "accepted"
    withdrawn = "withdrawn"
    discarded = "discarded"


class JobState(str, enum.Enum):
    pending = "pending"
    crawling = "crawling"
    extracting = "extracting"
    extracted = "extracted"
    generating = "generating"
    ready = "ready"
    failed = "failed"


class FailedStage(str, enum.Enum):
    crawl = "crawl"
    extract = "extract"
    generate = "generate"


class InterviewKind(str, enum.Enum):
    phone = "phone"
    video = "video"
    onsite = "onsite"
    technical = "technical"
    final = "final"


class InterviewOutcome(str, enum.Enum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    cancelled = "cancelled"


class ChatRole(str, enum.Enum):
    user = "user"
    assistant = "assistant"
    system = "system"


class LabelCategory(str, enum.Enum):
    role = "role"
    tech = "tech"
    domain = "domain"
    seniority = "seniority"
    work_mode = "work_mode"
    location = "location"
    company_size = "company_size"
    language = "language"
    company = "company"
    other = "other"


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


application_label = Table(
    "application_label",
    Base.metadata,
    Column(
        "application_id",
        UUID(as_uuid=True),
        ForeignKey("application.id"),
        primary_key=True,
    ),
    Column(
        "label_id",
        UUID(as_uuid=True),
        ForeignKey("label.id"),
        primary_key=True,
    ),
)


class Label(Base):
    __tablename__ = "label"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)
    color: Mapped[str] = mapped_column(String(7))
    is_auto: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    category: Mapped["LabelCategory"] = mapped_column(
        Enum(LabelCategory, name="labelcategory"),
        nullable=False,
        default=LabelCategory.other,
        server_default=LabelCategory.other.value,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


@event.listens_for(Label, "init")
def _label_init(target: Label, args: tuple, kwargs: dict) -> None:
    kwargs.setdefault("is_auto", False)


class User(Base):
    __tablename__ = "user"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    ms_oid: Mapped[str] = mapped_column(String(64), unique=True)
    email: Mapped[str] = mapped_column(String(320))
    display_name: Mapped[str] = mapped_column(String(200))
    ms_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CVVariant(Base):
    __tablename__ = "cv_variant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_md: Mapped[str] = mapped_column(Text)
    file_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class AnschreibenVariant(Base):
    __tablename__ = "anschreiben_variant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    name: Mapped[str] = mapped_column(String(200))
    source_md: Mapped[str] = mapped_column(Text)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Application(Base):
    __tablename__ = "application"
    __table_args__ = (UniqueConstraint("user_id", "url_hash", name="uq_user_url_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    display_id: Mapped[int] = mapped_column(
        Integer,
        SASequence("application_display_id_seq"),
        unique=True,
        nullable=False,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    url: Mapped[str] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[ApplicationStatus] = mapped_column(
        Enum(ApplicationStatus), default=ApplicationStatus.draft
    )
    cv_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("cv_variant.id"), nullable=True
    )
    anschreiben_variant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("anschreiben_variant.id"), nullable=True
    )
    generated_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_docx_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(2), nullable=True)
    job_state: Mapped[JobState] = mapped_column(Enum(JobState), default=JobState.pending)
    job_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    failed_stage: Mapped[FailedStage | None] = mapped_column(
        Enum(FailedStage), nullable=True
    )
    job_posting_dirty: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    posting_online: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    posting_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    inquiry_subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    inquiry_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    inquiry_sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    discard_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    job_posting: Mapped[JobPosting | None] = relationship(
        "JobPosting", uselist=False, back_populates="application"
    )
    labels: Mapped[list[Label]] = relationship(
        "Label", secondary=application_label, lazy="selectin"
    )


class JobPosting(Base):
    __tablename__ = "job_posting"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id"), unique=True
    )
    raw_text: Mapped[str] = mapped_column(Text)
    raw_html_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    company: Mapped[str | None] = mapped_column(Text, nullable=True)
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deadline: Mapped[str | None] = mapped_column(Text, nullable=True)
    salary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_stack: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    seniority: Mapped[str | None] = mapped_column(Text, nullable=True)
    work_mode: Mapped[str | None] = mapped_column(Text, nullable=True)
    benefits: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    required_documents: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    mentions_home_office_policy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mentions_part_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    backfill_attempts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    extracted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped[Application] = relationship("Application", back_populates="job_posting")


class Interview(Base):
    __tablename__ = "interview"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application.id"))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    kind: Mapped[InterviewKind] = mapped_column(Enum(InterviewKind))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[InterviewOutcome] = mapped_column(
        Enum(InterviewOutcome), default=InterviewOutcome.pending
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ChatMessage(Base):
    __tablename__ = "chat_message"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("application.id"))
    role: Mapped[ChatRole] = mapped_column(Enum(ChatRole))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Session(Base):
    __tablename__ = "session"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class InquiryPromptTemplate(Base):
    __tablename__ = "inquiry_prompt_template"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), unique=True)
    source_md: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
