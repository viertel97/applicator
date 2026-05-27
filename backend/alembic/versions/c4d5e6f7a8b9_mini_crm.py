"""mini CRM: interaction, discard_reason, application_event

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
Create Date: 2026-05-27 00:00:00.000000

Drops application.{inquiry_subject, inquiry_body, inquiry_sent_at}; the
inquiry_subject/body content is preserved by being copied into a new
interaction row per application (created_from='inquiry_migration').
Renames application.discard_reason (text) -> discard_note (text); the
existing free-text content is preserved verbatim.
"""
import uuid as _uuid
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4d5e6f7a8b9"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SYSTEM_REASONS = [
    ("no_reply",        "No reply",          10),
    ("rejected",        "Rejected",          20),
    ("withdrew_self",   "Withdrew myself",   30),
    ("location",        "Location mismatch", 40),
    ("salary",          "Salary mismatch",   50),
    ("tech_mismatch",   "Tech mismatch",     60),
    ("seniority",       "Seniority mismatch", 70),
    ("posting_offline", "Posting offline",   80),
    ("duplicate",       "Duplicate",         90),
    ("other",           "Other",             100),
]


def upgrade() -> None:
    bind = op.get_bind()

    direction = postgresql.ENUM(
        "out", "in", name="interactiondirection", create_type=False
    )
    channel = postgresql.ENUM(
        "mail", "linkedin", "phone", "portal", "xing", "other",
        name="interactionchannel", create_type=False,
    )
    sentiment = postgresql.ENUM(
        "positive", "neutral", "negative", "rejection",
        name="interactionsentiment", create_type=False,
    )
    created_from = postgresql.ENUM(
        "manual", "inquiry_migration", "graph_sync",
        name="interactioncreatedfrom", create_type=False,
    )
    event_kind = postgresql.ENUM(
        "status_change", "created", "inquiry_generated", "interview_scheduled",
        name="applicationeventkind", create_type=False,
    )
    for e in (direction, channel, sentiment, created_from, event_kind):
        e.create(bind, checkfirst=True)

    op.create_table(
        "discard_reason",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "slug", name="uq_discard_user_slug"),
    )

    op.create_table(
        "interaction",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("application.id"), nullable=False),
        sa.Column("occurred_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("direction", direction, nullable=False),
        sa.Column("channel", channel, nullable=False),
        sa.Column("subject", sa.Text()),
        sa.Column("body", sa.Text()),
        sa.Column("contact_name", sa.Text()),
        sa.Column("contact_handle", sa.Text()),
        sa.Column("sentiment", sentiment, nullable=True),
        sa.Column("created_from", created_from, nullable=False, server_default="manual"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_interaction_app", "interaction", ["application_id"])
    op.create_index(
        "ix_interaction_app_occurred",
        "interaction",
        ["application_id", sa.text("occurred_at DESC")],
    )

    op.create_table(
        "application_event",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("application_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("application.id"), nullable=False),
        sa.Column("kind", event_kind, nullable=False),
        sa.Column("from_value", sa.String(64)),
        sa.Column("to_value", sa.String(64)),
        sa.Column("meta", sa.JSON()),
        sa.Column("occurred_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_appevent_app", "application_event", ["application_id"])
    op.create_index("ix_appevent_occurred", "application_event", ["occurred_at"])

    # application FK additions + rename + drops
    op.add_column("application",
                  sa.Column("discard_reason_id", postgresql.UUID(as_uuid=True),
                            sa.ForeignKey("discard_reason.id"), nullable=True))
    op.add_column("application",
                  sa.Column("discard_interaction_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_app_discard_interaction",
        "application", "interaction",
        ["discard_interaction_id"], ["id"],
        use_alter=True,
    )
    op.create_index(
        "ix_app_discard_reason_id", "application", ["discard_reason_id"]
    )
    op.create_index(
        "ix_app_discard_interaction_id", "application", ["discard_interaction_id"]
    )
    op.alter_column("application", "discard_reason", new_column_name="discard_note")

    # ----- backfill -----
    # 1. seed system reasons per user
    users = bind.execute(sa.text("SELECT id FROM \"user\"")).fetchall()
    for u in users:
        for slug, label, sort in SYSTEM_REASONS:
            bind.execute(
                sa.text(
                    "INSERT INTO discard_reason "
                    "(id, user_id, slug, label, is_system, sort_order) "
                    "VALUES (:i, :u, :s, :l, true, :o) "
                    "ON CONFLICT (user_id, slug) DO NOTHING"
                ),
                {"i": _uuid.uuid4(), "u": u.id, "s": slug, "l": label, "o": sort},
            )

    # 2. backfill inquiry rows into interaction
    inquiries = bind.execute(sa.text(
        "SELECT id, inquiry_subject, inquiry_body, inquiry_sent_at "
        "FROM application WHERE inquiry_sent_at IS NOT NULL"
    )).fetchall()
    for row in inquiries:
        bind.execute(
            sa.text(
                "INSERT INTO interaction "
                "(id, application_id, occurred_at, direction, channel, "
                "subject, body, created_from) "
                "VALUES (:i, :a, :o, 'out', 'mail', :s, :b, 'inquiry_migration')"
            ),
            {
                "i": _uuid.uuid4(),
                "a": row.id,
                "o": row.inquiry_sent_at,
                "s": row.inquiry_subject,
                "b": row.inquiry_body,
            },
        )

    # 3. map discarded apps' discard_note to a seeded reason where the text
    #    matches a system label case-insensitively
    bind.execute(sa.text(
        """
        UPDATE application a SET discard_reason_id = dr.id
          FROM discard_reason dr
         WHERE a.user_id = dr.user_id
           AND a.status::text = 'discarded'
           AND a.discard_note IS NOT NULL
           AND lower(trim(a.discard_note)) = lower(dr.label)
        """
    ))

    # 4. one application_event row per application: kind=created
    rows = bind.execute(sa.text("SELECT id, created_at FROM application")).fetchall()
    for row in rows:
        bind.execute(
            sa.text(
                "INSERT INTO application_event "
                "(id, application_id, kind, occurred_at) "
                "VALUES (:i, :a, 'created', :o)"
            ),
            {"i": _uuid.uuid4(), "a": row.id, "o": row.created_at},
        )

    # ----- drop legacy columns -----
    op.drop_column("application", "inquiry_subject")
    op.drop_column("application", "inquiry_body")
    op.drop_column("application", "inquiry_sent_at")


def downgrade() -> None:
    # destructive: inquiry backfill data is not reconstructible
    op.add_column("application", sa.Column("inquiry_subject", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("inquiry_body", sa.Text(), nullable=True))
    op.add_column("application", sa.Column("inquiry_sent_at", sa.DateTime(), nullable=True))
    op.drop_index("ix_app_discard_interaction_id", table_name="application")
    op.drop_index("ix_app_discard_reason_id", table_name="application")
    op.drop_constraint("fk_app_discard_interaction", "application", type_="foreignkey")
    op.drop_column("application", "discard_interaction_id")
    op.drop_column("application", "discard_reason_id")
    op.alter_column("application", "discard_note", new_column_name="discard_reason")
    op.drop_index("ix_appevent_occurred", table_name="application_event")
    op.drop_index("ix_appevent_app", table_name="application_event")
    op.drop_table("application_event")
    op.drop_index("ix_interaction_app_occurred", table_name="interaction")
    op.drop_index("ix_interaction_app", table_name="interaction")
    op.drop_table("interaction")
    op.drop_table("discard_reason")
    for name in (
        "applicationeventkind", "interactioncreatedfrom",
        "interactionsentiment", "interactionchannel", "interactiondirection",
    ):
        op.execute(f"DROP TYPE IF EXISTS {name}")
