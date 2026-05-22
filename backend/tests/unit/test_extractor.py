import json

from app.extractor import extract
from app.extractor.schemas import ExtractedJobPosting
from tests.fakes.llm import FakeLLM


def test_extract_parses_json():
    payload = {
        "title": "Senior Engineer",
        "company": "Acme",
        "location": "Berlin",
        "description": "Build stuff",
        "requirements": "Python",
        "tech_stack": ["python", "fastapi"],
        "language": "en",
    }
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = extract("blob", llm)
    assert isinstance(result, ExtractedJobPosting)
    assert result.title == "Senior Engineer"
    assert result.tech_stack == ["python", "fastapi"]
    assert result.language == "en"


def test_extract_passes_schema_to_llm():
    captured = {}

    def handler(messages, schema):
        captured["schema"] = schema
        return '{"language":"de"}'

    extract("blob", FakeLLM(handler=handler))
    assert captured["schema"]["properties"]["title"]["anyOf"][0]["type"] == "string"


def test_extract_parses_inquiry_flags():
    payload = {
        "language": "de",
        "mentions_home_office_policy": True,
        "mentions_part_time": False,
    }
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = extract("blob", llm)
    assert result.mentions_home_office_policy is True
    assert result.mentions_part_time is False


def test_extract_inquiry_flags_default_to_false():
    payload = {"language": "de"}
    llm = FakeLLM(handler=lambda m, s: json.dumps(payload))
    result = extract("blob", llm)
    assert result.mentions_home_office_policy is False
    assert result.mentions_part_time is False
