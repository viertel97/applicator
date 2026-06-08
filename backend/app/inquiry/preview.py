from app.extractor.schemas import ContactInfo, ExtractedJobPosting
from app.inquiry.prompts import _topic_lines, build_body, user_prompt

SAMPLE_JOB = ExtractedJobPosting(
    title="Data Engineer",
    company="Acme GmbH",
    contact=ContactInfo(name="Müller"),
    reference_number="7",
    language="de",
)
SAMPLE_GREETING = {"de": "Sehr geehrte Frau Müller", "en": "Dear Ms Müller"}
SAMPLE_SUBJECT = {
    "de": "Offene Fragen – Data Engineer (Ref. 7)",
    "en": "Open questions – Data Engineer (Ref. 7)",
}


def _render_lang(
    lang: str,
    *,
    source_md: str,
    user_prompt_md: str | None,
    ho_de: str | None,
    ho_en: str | None,
    pt_de: str | None,
    pt_en: str | None,
    body_de: str | None,
    body_en: str | None,
) -> dict:
    up = user_prompt(
        job=SAMPLE_JOB,
        language=lang,
        ask_home_office=True,
        ask_part_time=True,
        template=user_prompt_md or None,
        ho_de=ho_de,
        ho_en=ho_en,
        pt_de=pt_de,
        pt_en=pt_en,
    )
    topics = _topic_lines(lang, True, True, ho_de, ho_en, pt_de, pt_en)
    body_tpl = (body_en if lang == "en" else body_de) or None
    email = build_body(
        greeting=SAMPLE_GREETING[lang],
        title=SAMPLE_JOB.title or "",
        ref_number=SAMPLE_JOB.reference_number,
        questions=topics,
        language=lang,
        template=body_tpl,
        company=SAMPLE_JOB.company,
    )
    return {
        "system_prompt": source_md,
        "user_prompt": up,
        "subject": SAMPLE_SUBJECT[lang],
        "greeting": SAMPLE_GREETING[lang],
        "questions": topics,
        "email": email,
    }


def build_preview(
    *,
    source_md: str,
    user_prompt_md: str | None = None,
    question_home_office_de: str | None = None,
    question_home_office_en: str | None = None,
    question_part_time_de: str | None = None,
    question_part_time_en: str | None = None,
    body_template_de: str | None = None,
    body_template_en: str | None = None,
) -> dict:
    kw = dict(
        source_md=source_md,
        user_prompt_md=user_prompt_md,
        ho_de=question_home_office_de,
        ho_en=question_home_office_en,
        pt_de=question_part_time_de,
        pt_en=question_part_time_en,
        body_de=body_template_de,
        body_en=body_template_en,
    )
    return {"de": _render_lang("de", **kw), "en": _render_lang("en", **kw)}
