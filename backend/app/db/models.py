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
    need_call = "need_call"
    apply_direct = "apply_direct"
    interview = "interview"


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


class InteractionDirection(str, enum.Enum):
    out = "out"
    in_ = "in"


class InteractionChannel(str, enum.Enum):
    mail = "mail"
    linkedin = "linkedin"
    phone = "phone"
    portal = "portal"
    xing = "xing"
    interview = "interview"
    other = "other"


class InteractionSentiment(str, enum.Enum):
    positive = "positive"
    neutral = "neutral"
    negative = "negative"
    rejection = "rejection"


class InteractionCreatedFrom(str, enum.Enum):
    manual = "manual"
    inquiry_migration = "inquiry_migration"
    graph_sync = "graph_sync"
    eml_import = "eml_import"
    inquiry_sent = "inquiry_sent"
    email_webhook = "email_webhook"


class InterviewStage(str, enum.Enum):
    phone_screen = "phone_screen"
    technical = "technical"
    onsite = "onsite"
    hr = "hr"
    final = "final"
    other = "other"


class ApplicationEventKind(str, enum.Enum):
    status_change = "status_change"
    created = "created"
    inquiry_generated = "inquiry_generated"
    interview_scheduled = "interview_scheduled"


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
    ingest_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    calendar_token: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
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
    posting_offline_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    posting_offline_dismissed_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )
    discard_reason_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("discard_reason.id"), nullable=True
    )
    discard_interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interaction.id", use_alter=True, name="fk_app_discard_interaction"),
        nullable=True,
    )
    discard_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
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
    reference_number: Mapped[str | None] = mapped_column(Text, nullable=True)
    mentions_home_office_policy: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mentions_part_time: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    backfill_attempts: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    extracted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    application: Mapped[Application] = relationship("Application", back_populates="job_posting")


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
    user_prompt_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_home_office_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_home_office_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_part_time_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_part_time_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_template_de: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_template_en: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class DiscardReason(Base):
    __tablename__ = "discard_reason"
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_discard_user_slug"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Interaction(Base):
    __tablename__ = "interaction"
    __table_args__ = (
        # Idempotent upsert key for externally-synced interactions (e.g. MS
        # Graph calendar events). Partial-unique semantics are enforced in code
        # (both null for manual rows); the constraint guards the sync path.
        UniqueConstraint(
            "external_source", "external_id", name="uq_interaction_external"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id"), index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    direction: Mapped[InteractionDirection] = mapped_column(
        # in_ → "in": persist enum values, not member names, to match the
        # migration-created Postgres type (values "in"/"out").
        Enum(
            InteractionDirection,
            name="interactiondirection",
            values_callable=lambda e: [m.value for m in e],
        )
    )
    channel: Mapped[InteractionChannel] = mapped_column(
        Enum(InteractionChannel, name="interactionchannel")
    )
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    contact_handle: Mapped[str | None] = mapped_column(Text, nullable=True)
    sentiment: Mapped[InteractionSentiment | None] = mapped_column(
        Enum(InteractionSentiment, name="interactionsentiment"), nullable=True
    )
    interview_stage: Mapped[InterviewStage | None] = mapped_column(
        # Only meaningful when channel == 'interview'. Persist enum values,
        # not member names, to match the migration-created Postgres type.
        Enum(
            InterviewStage,
            name="interviewstage",
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=True,
    )
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    needs_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_from: Mapped[InteractionCreatedFrom] = mapped_column(
        Enum(InteractionCreatedFrom, name="interactioncreatedfrom"),
        default=InteractionCreatedFrom.manual,
        server_default=InteractionCreatedFrom.manual.value,
    )
    # Provenance of an externally-synced interaction. `external_source` is a
    # plain string (e.g. "ms_graph") and `external_id` the source's stable id
    # (Graph event id); together they key an idempotent upsert. Both null for
    # manually-created rows.
    external_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CalendarSyncState(Base):
    """One row per synced external calendar; holds the delta cursor.

    `delta_link` is the opaque MS Graph ``@odata.deltaLink`` used to fetch only
    changes since the last sync. Null before the first full sync (or after a
    410 reset).
    """

    __tablename__ = "calendar_sync_state"
    __table_args__ = (
        UniqueConstraint("user_id", "calendar_id", name="uq_calsync_user_calendar"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"), index=True)
    calendar_id: Mapped[str] = mapped_column(String(255), nullable=False)
    delta_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class ApplicationEvent(Base):
    __tablename__ = "application_event"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("application.id"), index=True
    )
    # Set when a webhook creates this event for an interview it scheduled;
    # ON DELETE CASCADE so rejecting (deleting) that interview also removes
    # this timeline note. Null for events not tied to a specific interaction.
    interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interaction.id", ondelete="CASCADE"), nullable=True, index=True
    )
    kind: Mapped[ApplicationEventKind] = mapped_column(
        Enum(ApplicationEventKind, name="applicationeventkind")
    )
    from_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    to_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )


class WebhookRequest(Base):
    """Audit record of a single inbound-email webhook request.

    Written on EVERY code path (success and failure). status/reason are plain
    strings following a documented convention (NO DB enum) to avoid enum-drift
    migration friction; the values are validated by tests, not the database.
    """

    __tablename__ = "webhook_request"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=_uuid
    )
    # Null when the ingest token did not match a user (bad/unknown token).
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("user.id"), nullable=True, index=True
    )
    ingest_token: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    headers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    raw_body: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    matched_application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application.id"), nullable=True
    )
    # Set on the `created` path to the Interaction this webhook produced;
    # ON DELETE SET NULL so rejecting (deleting) that interview just unlinks.
    created_interaction_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("interaction.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), index=True
    )
