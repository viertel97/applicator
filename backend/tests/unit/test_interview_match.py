from app.email_ingest.interview_match import match_application, Candidate


def _cands():
    return [
        Candidate(application_id="a1", company="Acme GmbH", url="https://acme.example/jobs/1"),
        Candidate(application_id="a2", company="Globex", url="https://globex.io/careers/9"),
    ]


def test_matches_by_sender_domain():
    aid, score = match_application(sender="jane@acme.example", subject="Interview",
                                   body="", candidates=_cands())
    assert aid == "a1"
    assert score > 0


def test_matches_by_company_name_in_subject():
    aid, score = match_application(sender="recruiter@hire.io",
                                   subject="Your Globex interview", body="", candidates=_cands())
    assert aid == "a2"
    assert score >= 0.8


def test_no_signal_returns_low_score():
    # SequenceMatcher produces a small non-zero ratio even for unrelated strings;
    # the real score is ~0.067. The webhook will treat scores below 0.1 as "no match".
    aid, score = match_application(
        sender="recruiter@hire.io", subject="Generic email", body="", candidates=_cands()
    )
    assert score < 0.1


def test_empty_candidates_returns_none():
    aid, score = match_application(sender="x@y.z", subject="", body="", candidates=[])
    assert aid is None
    assert score == 0.0
