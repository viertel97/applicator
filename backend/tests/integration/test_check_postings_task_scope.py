"""The check_postings task must only inspect draft applications."""
from app.db.models import Application, ApplicationStatus


def _app(db, user, slug, status):
    a = Application(
        user_id=user.id,
        url=f"https://x.test/{slug}",
        url_hash=f"h{slug}",
        status=status,
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def test_task_checks_only_drafts(db_session, auth_user, monkeypatch):
    _, u = auth_user
    draft = _app(db_session, u, "draft", ApplicationStatus.draft)
    applied = _app(db_session, u, "applied", ApplicationStatus.applied)
    interview = _app(db_session, u, "interview", ApplicationStatus.interview)

    from app.tasks import check_postings as cp

    monkeypatch.setattr(cp, "GroqClient", lambda **kw: object())
    monkeypatch.setattr(cp.time, "sleep", lambda *_: None)
    # Every checked posting is judged offline with a reason.
    monkeypatch.setattr(cp, "_check_one", lambda url, llm, fetch_fn=None: (False, "http_404"))

    result = cp.check_postings_task()

    assert result["checked"] == 1  # only the draft
    for a in (draft, applied, interview):
        db_session.refresh(a)
    assert draft.posting_online is False
    assert draft.posting_offline_reason == "http_404"
    assert applied.posting_online is None
    assert interview.posting_online is None


def test_task_clears_reason_when_back_online(db_session, auth_user, monkeypatch):
    _, u = auth_user
    a = _app(db_session, u, "back", ApplicationStatus.draft)
    a.posting_online = False
    a.posting_offline_reason = "http_404"
    db_session.commit()

    from app.tasks import check_postings as cp

    monkeypatch.setattr(cp, "GroqClient", lambda **kw: object())
    monkeypatch.setattr(cp.time, "sleep", lambda *_: None)
    monkeypatch.setattr(cp, "_check_one", lambda url, llm, fetch_fn=None: (True, None))

    cp.check_postings_task()

    db_session.refresh(a)
    assert a.posting_online is True
    assert a.posting_offline_reason is None
