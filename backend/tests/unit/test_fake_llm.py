from tests.fakes.llm import FakeLLM


def test_fake_records_calls():
    f = FakeLLM(handler=lambda m, s: "ok")
    out = f.complete([{"role": "user", "content": "hi"}])
    assert out == "ok"
    assert len(f.calls) == 1
