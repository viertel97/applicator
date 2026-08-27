"""The CalendarSuggestion ORM model is registered with the expected shape."""
from app.db.models import CalendarSuggestion, CalendarSuggestionStatus


def test_status_enum_values():
    assert [s.value for s in CalendarSuggestionStatus] == [
        "pending",
        "confirmed",
        "dismissed",
    ]


def test_table_columns():
    cols = set(CalendarSuggestion.__table__.columns.keys())
    assert {
        "id",
        "user_id",
        "external_source",
        "external_id",
        "status",
        "subject",
        "starts_at",
        "ends_at",
        "location",
        "body",
        "organizer_email",
        "suggested_application_id",
        "match_score",
        "interaction_id",
        "created_at",
        "updated_at",
    } <= cols


def test_unique_constraint_on_external_key():
    names = {c.name for c in CalendarSuggestion.__table__.constraints}
    assert "uq_calsuggestion_external" in names
