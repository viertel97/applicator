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
