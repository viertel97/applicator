import json

from app.extractor.schemas import ExtractedJobPosting
from app.inquiry import draft
from app.inquiry.schemas import InquiryEmail


def _job(**kw) -> ExtractedJobPosting:
    base = {"language": "de", "title": "Dev", "company": "Acme"}
    base.update(kw)
    return ExtractedJobPosting(**base)


class FakeLLM:
    def __init__(self, handler):
        self._handler = handler

    def complete(self, messages, **kwargs):
        return self._handler(messages, kwargs.get("json_schema"))


def test_draft_parses_llm_json_into_inquiry_email():
    payload = {"subject": "Frage", "body": "Hallo …"}
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = draft(
        job=_job(),
        language="de",
        ask_home_office=True,
        ask_part_time=True,
        system_md="SYS",
        llm=llm,
    )
    assert isinstance(result, InquiryEmail)
    assert result.subject == "Frage"
    assert result.body == "Hallo …"


def test_draft_uses_provided_system_prompt():
    seen = {}

    def handler(messages, schema):
        seen["sys"] = messages[0]["content"]
        return json.dumps({"subject": "s", "body": "b"})

    draft(
        job=_job(),
        language="de",
        ask_home_office=True,
        ask_part_time=False,
        system_md="CUSTOM-SYSTEM-PROMPT",
        llm=FakeLLM(handler=handler),
    )
    assert seen["sys"] == "CUSTOM-SYSTEM-PROMPT"
