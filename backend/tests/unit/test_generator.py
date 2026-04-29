from app.extractor.schemas import ExtractedJobPosting
from app.generator import generate
from tests.fakes.llm import FakeLLM


def test_generate_returns_text():
    job = ExtractedJobPosting(title="Eng", company="Acme", language="de")
    llm = FakeLLM(handler=lambda m, s: "# Anschreiben\n\nSehr geehrte...")
    out = generate(job, "cv md", "template md", "de", llm)
    assert out.startswith("# Anschreiben")


def test_generate_passes_language_in_prompt():
    job = ExtractedJobPosting(title="Eng", company="Acme", language="en")
    captured = {}

    def handler(messages, schema):
        captured["user"] = messages[1]["content"]
        return "letter"

    generate(job, "cv", "tpl", "en", FakeLLM(handler=handler))
    assert "Target language: en" in captured["user"]
    assert "=== CANDIDATE CV" in captured["user"]
