from app.tasks.check_postings import _check_one, _heuristic, _redirect_reason
from tests.fakes.llm import FakeLLM

JOB = "https://acme.example.com/jobs/senior-python-engineer-123"


def _h(status, text="", final_url=JOB, original=JOB):
    return _heuristic(status, text, final_url, original)


def test_heuristic_404_is_offline_with_reason():
    assert _h(404) == (False, "http_404")


def test_heuristic_403_is_offline_with_reason():
    assert _h(403) == (False, "http_403")


def test_heuristic_410_is_offline_with_reason():
    assert _h(410) == (False, "http_410")


def test_heuristic_200_no_keywords_is_online():
    assert _h(200, "Senior Python Engineer at Acme — apply now") == (True, None)


def test_heuristic_200_keyword_english_is_offline():
    online, reason = _h(200, "Sorry, this position has been filled.")
    assert online is False
    assert reason == "keyword:position has been filled"


def test_heuristic_new_german_keywords_are_offline():
    for kw in (
        "stellenanzeige konnte nicht gefunden werden",
        "keine stellenanzeige gefunden",
        "bereits besetzt",
    ):
        online, reason = _h(200, f"Hinweis: {kw}.")
        assert online is False, kw
        assert reason == f"keyword:{kw}"


def test_heuristic_503_is_inconclusive():
    assert _h(503, "Service Unavailable") == (None, None)


# --- redirect detection ---------------------------------------------------

def test_offhost_redirect_is_offline():
    final = "https://other-jobboard.example.org/listing/999"
    assert _h(200, "content", final_url=final) == (False, "redirect_offhost")


def test_root_redirect_is_offline():
    final = "https://acme.example.com/"
    assert _h(200, "content", final_url=final) == (False, "redirect_root")


def test_landing_path_redirect_is_offline():
    final = "https://acme.example.com/karriere"
    assert _h(200, "content", final_url=final) == (False, "redirect_root")


def test_same_host_deep_redirect_falls_through_to_keyword_llm():
    # A same-host redirect to another deep posting path is not itself offline;
    # it falls through to keyword/LLM (here: clean text → online).
    final = "https://acme.example.com/jobs/redirected-role-456"
    assert _h(200, "Great role, apply now", final_url=final) == (True, None)


def test_redirect_reason_none_when_no_redirect():
    assert _redirect_reason(JOB, JOB) is None


# --- _check_one -----------------------------------------------------------

def test_check_one_conclusive_heuristic_skips_llm():
    def fake_fetch(url):
        return 404, "", url

    llm = FakeLLM()
    assert _check_one(JOB, llm, fetch_fn=fake_fetch) == (False, "http_404")
    assert len(llm.calls) == 0


def test_check_one_inconclusive_falls_back_to_llm_online():
    def fake_fetch(url):
        return 503, "temporarily unavailable", url

    llm = FakeLLM(handler=lambda m, s: "yes")
    assert _check_one(JOB, llm, fetch_fn=fake_fetch) == (True, None)
    assert len(llm.calls) == 1


def test_check_one_llm_no_answer_sets_llm_inactive_reason():
    def fake_fetch(url):
        return 503, "error", url

    llm = FakeLLM(handler=lambda m, s: "no")
    assert _check_one(JOB, llm, fetch_fn=fake_fetch) == (False, "llm_inactive")


def test_check_one_fetch_error_returns_none():
    def fake_fetch(url):
        raise ConnectionError("no route to host")

    llm = FakeLLM()
    assert _check_one(JOB, llm, fetch_fn=fake_fetch) == (None, None)
    assert len(llm.calls) == 0


def test_check_one_clean_200_is_online_no_reason():
    def fake_fetch(url):
        return 200, "Apply now for this role", url

    llm = FakeLLM()
    assert _check_one(JOB, llm, fetch_fn=fake_fetch) == (True, None)
    assert len(llm.calls) == 0
