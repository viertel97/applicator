from app.db.models import ApplicationEvent


def test_application_event_has_interaction_fk_cascade():
    col = ApplicationEvent.__table__.columns["interaction_id"]
    assert col.nullable is True
    fk = next(iter(col.foreign_keys))
    assert fk.column.table.name == "interaction"
    assert fk.ondelete == "CASCADE"


def test_application_event_construct_without_interaction():
    ev = ApplicationEvent()
    assert ev.interaction_id is None
