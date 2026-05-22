from unittest.mock import MagicMock

import pytest

from app.db.models import LabelCategory
from app.extractor.schemas import LabelSuggestions


def _stub_app():
    """Application stub: only `.labels` matters for the test."""
    app = MagicMock()
    app.labels = []
    return app


class _StubLabel:
    def __init__(self, name, category):
        self.name = name
        self.category = category


def test_upsert_creates_labels_with_correct_category(monkeypatch):
    from app.labels import upsert as upsert_mod

    created: list[tuple[str, LabelCategory]] = []
    by_name: dict[str, _StubLabel] = {}

    def fake_get_or_create(_db, name, category):
        if name not in by_name:
            by_name[name] = _StubLabel(name, category)
            created.append((name, category))
        return by_name[name]

    monkeypatch.setattr(upsert_mod, "_get_or_create_label", fake_get_or_create)

    app = _stub_app()
    sug = LabelSuggestions(
        role=["AI Engineer"],
        tech=["Python", "AWS"],
        company_size=["Konzern"],
    )
    upsert_mod.upsert_and_assign_labels(MagicMock(), app, sug)

    assert ("AI Engineer", LabelCategory.role) in created
    assert ("Python", LabelCategory.tech) in created
    assert ("AWS", LabelCategory.tech) in created
    assert ("Konzern", LabelCategory.company_size) in created
    assert len(app.labels) == 4


def test_upsert_preserves_existing_category(monkeypatch):
    from app.labels import upsert as upsert_mod

    existing = _StubLabel("Python", LabelCategory.tech)
    by_name = {"Python": existing}

    def fake_get_or_create(_db, name, category):
        # existing match: do not change category
        return by_name.get(name) or _StubLabel(name, category)

    monkeypatch.setattr(upsert_mod, "_get_or_create_label", fake_get_or_create)

    app = _stub_app()
    sug = LabelSuggestions(role=["Python"])
    upsert_mod.upsert_and_assign_labels(MagicMock(), app, sug)

    assert existing.category == LabelCategory.tech  # not flipped to role


def test_upsert_idempotent_for_already_assigned(monkeypatch):
    from app.labels import upsert as upsert_mod

    existing = _StubLabel("Konzern", LabelCategory.company_size)

    def fake_get_or_create(_db, name, category):
        return existing

    monkeypatch.setattr(upsert_mod, "_get_or_create_label", fake_get_or_create)

    app = _stub_app()
    app.labels.append(existing)
    sug = LabelSuggestions(company_size=["Konzern"])
    upsert_mod.upsert_and_assign_labels(MagicMock(), app, sug)
    assert app.labels.count(existing) == 1


def test_upsert_accepts_dict_payload(monkeypatch):
    """Backfill hands in the raw LLM dict before pydantic validation."""
    from app.labels import upsert as upsert_mod

    monkeypatch.setattr(
        upsert_mod, "_get_or_create_label",
        lambda _db, name, category: _StubLabel(name, category),
    )

    app = _stub_app()
    upsert_mod.upsert_and_assign_labels(
        MagicMock(), app,
        {"tech": ["Python"], "role": ["Engineer"]},
    )
    names = {lab.name for lab in app.labels}
    assert names == {"Python", "Engineer"}
