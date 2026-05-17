from app.tasks.check_postings import _heuristic, _check_one
from tests.fakes.llm import FakeLLM


def test_heuristic_404_is_offline():
    assert _heuristic(404, "") is False


def test_heuristic_410_is_offline():
    assert _heuristic(410, "") is False


def test_heuristic_200_no_keywords_is_online():
    assert _heuristic(200, "Senior Python Engineer at Acme — apply now") is True


def test_heuristic_200_keyword_german_is_offline():
    assert _heuristic(200, "Diese Stelle ist leider nicht mehr verfügbar.") is False


def test_heuristic_200_keyword_english_is_offline():
    assert _heuristic(200, "Sorry, this position has been filled.") is False


def test_heuristic_503_is_inconclusive():
    assert _heuristic(503, "Service Unavailable") is None


def test_check_one_conclusive_heuristic_skips_llm():
    def fake_fetch(url):
        return 404, ""

    llm = FakeLLM()
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is False
    assert len(llm.calls) == 0


def test_check_one_inconclusive_falls_back_to_llm():
    def fake_fetch(url):
        return 503, "temporarily unavailable"

    llm = FakeLLM(handler=lambda m, s: "yes")
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is True
    assert len(llm.calls) == 1


def test_check_one_llm_no_answer():
    def fake_fetch(url):
        return 503, "error"

    llm = FakeLLM(handler=lambda m, s: "no")
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is False


def test_check_one_fetch_error_returns_none():
    def fake_fetch(url):
        raise ConnectionError("no route to host")

    llm = FakeLLM()
    result = _check_one("https://example.com/job", llm, fetch_fn=fake_fetch)
    assert result is None
    assert len(llm.calls) == 0
