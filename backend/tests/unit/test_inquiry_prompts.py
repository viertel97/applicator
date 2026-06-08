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


from app.inquiry.prompts import (
    DEFAULT_BODY_TEMPLATE_DE,
    DEFAULT_BODY_TEMPLATE_EN,
    build_body,
)


def test_build_body_default_de_matches_current_wording():
    out = build_body(
        greeting="Sehr geehrte Frau Müller",
        title="Entwickler",
        ref_number="123",
        questions=["Frage eins?", "Frage zwei?"],
        language="de",
    )
    assert out.startswith("Sehr geehrte Frau Müller,\n\n")
    assert "Ihre Stellenausschreibung als „Entwickler (Ref. 123)“." in out
    assert "zwei kurze Fragen:" in out
    assert "Frage eins?\nFrage zwei?" in out
    assert out.endswith("mit freundlichen Grüßen\nJanik Viertel")


def test_build_body_default_en_matches_current_wording():
    out = build_body(
        greeting="Dear Ms Smith",
        title="Developer",
        ref_number=None,
        questions=["Q one?", "Q two?"],
        language="en",
    )
    assert out.startswith("Dear Ms Smith,\n\n")
    assert 'the position of "Developer".' in out
    assert "a couple of questions:" in out
    assert out.endswith("Kind regards\nJanik Viertel")


def test_build_body_custom_template_substitutes_all_tokens():
    tpl = "{greeting}|{title}|{ref}|{company}|{reference_number}|{questions}"
    out = build_body(
        greeting="Hi",
        title="Dev",
        ref_number="42",
        questions=["a", "b"],
        language="en",
        template=tpl,
        company="Acme",
    )
    assert out == "Hi|Dev| (Ref. 42)|Acme|42|a\nb"


def test_build_body_stray_braces_are_safe():
    out = build_body(
        greeting="Hi",
        title="Dev",
        ref_number=None,
        questions=["a"],
        language="en",
        template="{greeting} {oops} {title}",
    )
    assert out == "Hi {oops} Dev"


def test_default_body_templates_are_nonempty():
    assert DEFAULT_BODY_TEMPLATE_DE.strip() and DEFAULT_BODY_TEMPLATE_EN.strip()
