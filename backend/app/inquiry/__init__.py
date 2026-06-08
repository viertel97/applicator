from app.extractor.schemas import ExtractedJobPosting
from app.inquiry.prompts import build_body, user_prompt, _topic_lines
from app.inquiry.schemas import InquiryEmail, InquiryLLMOutput
from app.llm.base import LLMClient


def draft(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
    system_md: str,
    llm: LLMClient,
    user_prompt_template: str | None = None,
    ho_de: str | None = None,
    ho_en: str | None = None,
    pt_de: str | None = None,
    pt_en: str | None = None,
    body_de: str | None = None,
    body_en: str | None = None,
) -> InquiryEmail:
    schema = InquiryLLMOutput.model_json_schema()
    raw = llm.complete(
        [
            {"role": "system", "content": system_md},
            {
                "role": "user",
                "content": user_prompt(
                    job=job,
                    language=language,
                    ask_home_office=ask_home_office,
                    ask_part_time=ask_part_time,
                    template=user_prompt_template,
                    ho_de=ho_de,
                    ho_en=ho_en,
                    pt_de=pt_de,
                    pt_en=pt_en,
                ),
            },
        ],
        json_schema=schema,
        temperature=0.3,
    )
    llm_out = InquiryLLMOutput.model_validate_json(raw)
    questions = _topic_lines(language, ask_home_office, ask_part_time, ho_de, ho_en, pt_de, pt_en)
    body = build_body(
        greeting=llm_out.greeting,
        title=job.title or "",
        ref_number=job.reference_number,
        questions=questions,
        language=language,
        template=(body_en if (language or "de").lower() == "en" else body_de),
        company=job.company,
    )
    return InquiryEmail(subject=llm_out.subject, body=body)
