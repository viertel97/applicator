from typing import Any

from app.extractor.prompts import SYSTEM, user_prompt
from app.extractor.schemas import ExtractedJobPosting
from app.llm.base import LLMClient


def extract(raw_text: str, llm: LLMClient) -> ExtractedJobPosting:
    schema = ExtractedJobPosting.model_json_schema()
    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user_prompt(raw_text)},
        ],
        json_schema=schema,
        temperature=0.0,
    )
    return ExtractedJobPosting.model_validate_json(raw)


def extract_fields(
    raw_text: str,
    fields: list[str],
    llm: LLMClient,
) -> dict[str, Any]:
    """Partial-field extraction stub — full implementation arrives with contact-backfill merge."""
    raise NotImplementedError("extract_fields requires contact-backfill branch")
