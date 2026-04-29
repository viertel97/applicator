from tests.fakes.llm import FakeLLM


def test_fake_records_calls():
    f = FakeLLM(handler=lambda m, s: "ok")
    out = f.complete([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert len(f.calls) == 1


def test_fake_default_handler_returns_fake_response():
    f = FakeLLM()
    assert f.complete([]) == "FAKE_RESPONSE"


def test_fake_records_schema_and_temperature():
    schema = {"type": "object"}
    f = FakeLLM(handler=lambda m, s: "x")
    f.complete([], json_schema=schema, temperature=0.7)
    assert f.calls[0][1] == schema
    assert f.calls[0][2] == 0.7
