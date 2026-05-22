import json
from unittest.mock import MagicMock, patch

from app.db.models import Label, LabelCategory


def _seed_labels(db, names_auto):
    """names_auto: list of (name, is_auto) tuples."""
    out = []
    for name, is_auto in names_auto:
        lab = Label(name=name, color="#fff", is_auto=is_auto)
        db.add(lab)
        out.append(lab)
    db.commit()
    return out


def test_task_categorizes_other_labels(db_session, monkeypatch):
    db = db_session
    _seed_labels(db, [
        ("Python", True),
        ("Frankfurt", True),
        ("Senior", True),
    ])

    fake_llm = MagicMock()
    fake_llm.complete.return_value = json.dumps({
        "Python": "tech",
        "Frankfurt": "location",
        "Senior": "seniority",
    })

    with patch("app.tasks.categorize_labels._build_groq_client", return_value=fake_llm):
        from app.tasks.categorize_labels import categorize_existing_labels_task
        result = categorize_existing_labels_task.run()

    assert result["updated"] == 3
    cats = {l.name: l.category for l in db.query(Label).all()}
    assert cats["Python"] == LabelCategory.tech
    assert cats["Frankfurt"] == LabelCategory.location
    assert cats["Senior"] == LabelCategory.seniority


def test_task_skips_user_created_labels(db_session, monkeypatch):
    db = db_session
    _seed_labels(db, [
        ("Custom User Label", False),
        ("Python", True),
    ])

    fake_llm = MagicMock()
    fake_llm.complete.return_value = json.dumps({"Python": "tech"})

    with patch("app.tasks.categorize_labels._build_groq_client", return_value=fake_llm):
        from app.tasks.categorize_labels import categorize_existing_labels_task
        categorize_existing_labels_task.run()

    db.expire_all()
    custom = db.query(Label).filter_by(name="Custom User Label").one()
    assert custom.category == LabelCategory.other  # untouched


def test_task_is_idempotent(db_session, monkeypatch):
    db = db_session
    _seed_labels(db, [("Python", True)])

    fake_llm = MagicMock()
    fake_llm.complete.return_value = json.dumps({"Python": "tech"})

    with patch("app.tasks.categorize_labels._build_groq_client", return_value=fake_llm):
        from app.tasks.categorize_labels import categorize_existing_labels_task
        categorize_existing_labels_task.run()
        result = categorize_existing_labels_task.run()

    # Second run: no rows still 'other' & is_auto, so updated stays at 0
    assert result["updated"] == 0
