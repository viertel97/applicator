from app.extractor.schemas import ExtractedJobPosting, LabelSuggestions


def test_label_suggestions_defaults_all_empty_lists():
    s = LabelSuggestions()
    for field in (
        "role", "tech", "domain", "seniority", "work_mode",
        "location", "company_size", "language", "company",
    ):
        assert getattr(s, field) == []


def test_label_suggestions_has_no_other_field():
    fields = LabelSuggestions.model_fields
    assert "other" not in fields


def test_extracted_job_posting_uses_label_suggestions():
    j = ExtractedJobPosting(language="de")
    assert isinstance(j.suggested_labels, LabelSuggestions)
    assert j.suggested_labels.tech == []
