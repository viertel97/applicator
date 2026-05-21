from typing import Any

from pydantic import create_model

from app.extractor.prompts import SYSTEM, SYSTEM_PARTIAL, user_prompt
from app.extractor.schemas import ContactInfo, ExtractedJobPosting
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
    """Extract a subset of fields from a posting.

    Returns a dict whose keys are exactly `fields`; values may be None when
    the LLM did not find the field. Nested models (currently only
    `contact`) are returned as plain dicts.
    """
    if not fields:
        raise ValueError("fields must be non-empty")

    base_fields = ExtractedJobPosting.model_fields
    unknown = [f for f in fields if f not in base_fields]
    if unknown:
        raise ValueError(f"unknown fields: {unknown}")

    partial_field_defs = {}
    for name in fields:
        info = base_fields[name]
        partial_field_defs[name] = (info.annotation, info.default)
    Partial = create_model("PartialExtract", **partial_field_defs)

    raw = llm.complete(
        [
            {"role": "system", "content": SYSTEM_PARTIAL},
            {"role": "user", "content": user_prompt(raw_text)},
        ],
        json_schema=Partial.model_json_schema(),
        temperature=0.0,
    )
    parsed = Partial.model_validate_json(raw)

    result: dict[str, Any] = {}
    for name in fields:
        value = getattr(parsed, name)
        if isinstance(value, ContactInfo):
            result[name] = value.model_dump()
        else:
            result[name] = value
    return result
