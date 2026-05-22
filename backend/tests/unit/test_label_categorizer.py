import json
from unittest.mock import MagicMock

from app.db.models import LabelCategory


def test_categorize_returns_name_to_category_map():
    from app.labels.categorize import categorize_names

    llm = MagicMock()
    llm.complete.return_value = json.dumps({
        "Python": "tech",
        "Frankfurt": "location",
        "Senior": "seniority",
        "Konzern": "company_size",
    })
    result = categorize_names(["Python", "Frankfurt", "Senior", "Konzern"], llm)
    assert result == {
        "Python": LabelCategory.tech,
        "Frankfurt": LabelCategory.location,
        "Senior": LabelCategory.seniority,
        "Konzern": LabelCategory.company_size,
    }


def test_categorize_drops_unknown_category_values():
    from app.labels.categorize import categorize_names

    llm = MagicMock()
    llm.complete.return_value = json.dumps({"Foo": "tech", "Bar": "not-a-real-cat"})
    result = categorize_names(["Foo", "Bar"], llm)
    assert result == {"Foo": LabelCategory.tech}


def test_categorize_returns_empty_on_invalid_json():
    from app.labels.categorize import categorize_names

    llm = MagicMock()
    llm.complete.return_value = "not json"
    assert categorize_names(["X"], llm) == {}


def test_categorize_does_not_emit_other_in_schema():
    """`other` must not be an option the LLM can return."""
    from app.labels.categorize import _build_schema

    schema = _build_schema(["Python", "Senior"])
    enum_values = schema["properties"]["Python"]["enum"]
    assert "other" not in enum_values
    assert "tech" in enum_values
    assert sorted(enum_values) == sorted([
        "role", "tech", "domain", "seniority", "work_mode",
        "location", "company_size", "language", "company",
    ])
