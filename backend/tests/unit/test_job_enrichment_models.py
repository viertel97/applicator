import uuid
from app.db.models import Label, application_label, Application


def test_label_model_has_expected_fields():
    label = Label(name="Startup", color="#6366f1")
    assert label.name == "Startup"
    assert label.color == "#6366f1"
    assert label.is_auto is False


def test_application_label_table_exists():
    cols = {c.name for c in application_label.columns}
    assert "application_id" in cols
    assert "label_id" in cols


def test_application_has_posting_online_field():
    app = Application(url="https://x.test/j", url_hash="h" * 64)
    assert app.posting_online is None
    assert app.posting_checked_at is None
