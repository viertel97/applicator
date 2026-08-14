from sqlalchemy.dialects import postgresql
from app.db.models import Interaction, User, InteractionCreatedFrom


def _col_type(model, name):
    return model.__table__.c[name].type


def test_created_from_has_email_webhook_value():
    assert InteractionCreatedFrom.email_webhook.value == "email_webhook"


def test_created_from_binds_values_not_names():
    bind = _col_type(Interaction, "created_from").bind_processor(postgresql.dialect())
    assert bind(InteractionCreatedFrom.email_webhook) == "email_webhook"


def test_interaction_has_new_columns():
    cols = Interaction.__table__.c
    assert "location" in cols and cols["location"].nullable
    assert "ends_at" in cols and cols["ends_at"].nullable
    assert "needs_review" in cols
    assert cols["needs_review"].nullable is False
    assert cols["needs_review"].server_default is not None
    assert cols["needs_review"].server_default.arg == "false"


def test_user_has_token_columns():
    cols = User.__table__.c
    assert "ingest_token" in cols and cols["ingest_token"].nullable
    assert "calendar_token" in cols and cols["calendar_token"].nullable
    assert cols["ingest_token"].unique
    assert cols["calendar_token"].unique
