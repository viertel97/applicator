from app.db.models import Application


def _make_app(db_session, user, slug):
    a = Application(user_id=user.id, url=f"https://x.test/{slug}", url_hash=slug)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_create_and_read_interview_stage(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "istage")
    r = client.post(
        f"/api/applications/{a.id}/interactions",
        json={
            "direction": "in",
            "channel": "interview",
            "subject": "Screen",
            "interview_stage": "technical",
            "occurred_at": "2026-07-01T10:00:00+00:00",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["interaction"]["interview_stage"] == "technical"


def _log_interview(client, aid, occurred_at, stage=None):
    body = {"direction": "in", "channel": "interview", "occurred_at": occurred_at}
    if stage:
        body["interview_stage"] = stage
    r = client.post(f"/api/applications/{aid}/interactions", json=body)
    assert r.status_code == 200, r.text


def _set_status(client, aid, status):
    r = client.patch(f"/api/applications/{aid}", json={"status": status})
    assert r.status_code == 200, r.text


def test_summary_none_when_not_interview_status(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s1")
    _log_interview(client, a.id, "2026-07-01T10:00:00+00:00", "technical")
    got = client.get(f"/api/applications/{a.id}").json()
    assert got["interview_summary"] is None


def test_summary_none_when_no_interviews(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s2")
    _set_status(client, a.id, "interview")
    got = client.get(f"/api/applications/{a.id}").json()
    assert got["interview_summary"] is None


def test_summary_upcoming_and_past_rounds(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s3")
    _set_status(client, a.id, "interview")
    _log_interview(client, a.id, "2020-01-01T10:00:00+00:00", "phone_screen")  # R1 past
    _log_interview(client, a.id, "2999-01-01T10:00:00+00:00", "technical")     # R2 future
    s = client.get(f"/api/applications/{a.id}").json()["interview_summary"]
    assert s["rounds_logged"] == 2
    assert s["next"]["round"] == 2
    assert s["next"]["stage"] == "technical"
    assert s["last"]["round"] == 1
    assert s["last"]["stage"] == "phone_screen"


def test_summary_present_in_list(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u, "s4")
    _set_status(client, a.id, "interview")
    _log_interview(client, a.id, "2020-01-01T10:00:00+00:00", "onsite")
    rows = client.get("/api/applications").json()
    row = next(r for r in rows if r["id"] == str(a.id))
    assert row["interview_summary"]["last"]["round"] == 1
    assert row["interview_summary"]["last"]["stage"] == "onsite"
    assert row["interview_summary"]["next"] is None
