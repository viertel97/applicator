from app.extractor.schemas import ContactInfo, ExtractedJobPosting


def test_extracted_job_posting_has_contact_block_not_flat_fields():
    fields = ExtractedJobPosting.model_fields
    assert "contact" in fields
    assert "contact_person" not in fields
    assert "application_email" not in fields


def test_contact_info_all_optional():
    c = ContactInfo()
    assert c.name is None and c.role is None and c.email is None and c.phone is None
    c2 = ContactInfo(name="Jane", email="j@x.com")
    assert c2.role is None and c2.phone is None


def test_extracted_job_posting_contact_default_none():
    j = ExtractedJobPosting(language="de")
    assert j.contact is None


import json
from unittest.mock import MagicMock

from app.extractor import extract_fields


def _fake_llm(payload: dict) -> MagicMock:
    llm = MagicMock()
    llm.complete.return_value = json.dumps(payload)
    return llm


def test_extract_fields_returns_only_requested_keys():
    llm = _fake_llm({"salary": "60-70k", "deadline": "2026-06-01"})
    result = extract_fields("posting text", ["salary", "deadline"], llm)
    assert set(result.keys()) == {"salary", "deadline"}
    assert result["salary"] == "60-70k"
    assert result["deadline"] == "2026-06-01"


def test_extract_fields_nested_contact():
    llm = _fake_llm({"contact": {"name": "Jane", "email": "j@x.com"}})
    result = extract_fields("posting text", ["contact"], llm)
    assert result["contact"] == {
        "name": "Jane",
        "role": None,
        "email": "j@x.com",
        "phone": None,
    }


def test_extract_fields_missing_returns_none():
    llm = _fake_llm({})
    result = extract_fields("posting text", ["salary"], llm)
    assert result == {"salary": None}


def test_extract_fields_empty_list_raises():
    import pytest

    with pytest.raises(ValueError):
        extract_fields("text", [], _fake_llm({}))
