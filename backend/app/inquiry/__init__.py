from app.extractor.schemas import ExtractedJobPosting
from app.inquiry.prompts import user_prompt
from app.inquiry.schemas import InquiryEmail
from app.llm.base import LLMClient


def draft(
    *,
    job: ExtractedJobPosting,
    language: str,
    ask_home_office: bool,
    ask_part_time: bool,
    system_md: str,
    llm: LLMClient,
) -> InquiryEmail:
    schema = InquiryEmail.model_json_schema()
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
                ),
            },
        ],
        json_schema=schema,
        temperature=0.3,
    )
    return InquiryEmail.model_validate_json(raw)
