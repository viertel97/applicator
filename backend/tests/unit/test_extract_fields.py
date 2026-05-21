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
