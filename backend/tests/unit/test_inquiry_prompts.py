from app.extractor.schemas import ExtractedJobPosting
from app.inquiry.prompts import DEFAULT_TEMPLATE, user_prompt


def _job(**kw) -> ExtractedJobPosting:
    base = {"language": "de", "title": "Dev", "company": "Acme"}
    base.update(kw)
    return ExtractedJobPosting(**base)


def test_default_template_is_non_empty_string():
    assert isinstance(DEFAULT_TEMPLATE, str) and len(DEFAULT_TEMPLATE) > 0


def test_user_prompt_includes_only_home_office_when_only_ho_missing():
    p = user_prompt(
        job=_job(), language="de", ask_home_office=True, ask_part_time=False,
    )
    assert "Home Office" in p or "home office" in p.lower()
    assert "80" not in p and "Teilzeit" not in p


def test_user_prompt_includes_only_part_time_when_only_pt_missing():
    p = user_prompt(
        job=_job(), language="de", ask_home_office=False, ask_part_time=True,
    )
    assert "80" in p or "Teilzeit" in p
    assert "Home Office" not in p and "home office" not in p.lower()


def test_user_prompt_includes_both_when_both_missing():
    p = user_prompt(
        job=_job(), language="en", ask_home_office=True, ask_part_time=True,
    )
    text = p.lower()
    assert ("home office" in text or "homeoffice" in text)
    assert ("80" in p or "teilzeit" in text or "part-time" in text)


def test_user_prompt_carries_language_and_company():
    p = user_prompt(
        job=_job(company="Acme GmbH"), language="en",
        ask_home_office=True, ask_part_time=False,
    )
    assert "Acme GmbH" in p
    assert "en" in p
