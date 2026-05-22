def test_label_has_category_column():
    from app.db.models import Label, LabelCategory
    cols = {c.name for c in Label.__table__.columns}
    assert "category" in cols
    col = Label.__table__.columns["category"]
    assert col.nullable is False
    # server_default carries the literal string, not the enum member
    assert col.server_default is not None
    assert "other" in str(col.server_default.arg)


def test_label_default_instance_category_other():
    from app.db.models import Label, LabelCategory
    label = Label(name="x", color="#fff")
    # Python-side default flows from the column default; we explicitly test
    # by reading the default expression
    assert Label.__table__.columns["category"].default.arg is LabelCategory.other
