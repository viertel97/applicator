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
