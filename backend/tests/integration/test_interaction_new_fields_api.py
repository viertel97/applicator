import uuid
from datetime import datetime, timezone

from app.db.models import Application, User


def _make_app(db_session, user):
    a = Application(user_id=user.id, url="https://x.test/i", url_hash=uuid.uuid4().hex)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def _other_users_app(db_session):
    other = User(ms_oid="other", email="other@x.c", display_name="Other")
    db_session.add(other)
    db_session.flush()
    a = Application(user_id=other.id, url="https://y.test/j", url_hash=uuid.uuid4().hex)
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)
    return a


def test_create_interview_with_location_and_ends_at(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u)

    occurred = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    ends = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)

    payload = {
        "direction": "in",
        "channel": "interview",
        "interview_stage": "onsite",
        "occurred_at": occurred.isoformat(),
        "ends_at": ends.isoformat(),
        "location": "Berlin HQ, Room 42",
    }
    r = client.post(f"/api/applications/{a.id}/interactions", json=payload)
    assert r.status_code in (200, 201), r.text

    body = r.json()
    interaction = body["interaction"]
    assert interaction["location"] == "Berlin HQ, Room 42"
    assert interaction["ends_at"].startswith("2026-09-01T15:00")
    assert interaction["needs_review"] is False


def test_patch_reassigns_application_and_clears_review(client, db_session, auth_user):
    _, u = auth_user
    app_a = _make_app(db_session, u)
    app_b = _make_app(db_session, u)

    # Create an interaction on app_a
    cr = client.post(
        f"/api/applications/{app_a.id}/interactions",
        json={"direction": "out", "channel": "mail", "body": "initial"},
    )
    assert cr.status_code in (200, 201), cr.text
    iid = cr.json()["interaction"]["id"]

    # PATCH: reassign to app_b and clear needs_review
    pr = client.patch(
        f"/api/interactions/{iid}",
        json={"application_id": str(app_b.id), "needs_review": False},
    )
    assert pr.status_code == 200, pr.text
    result = pr.json()
    assert result["application_id"] == str(app_b.id)
    assert result["needs_review"] is False


def test_patch_reassign_to_foreign_app_404(client, db_session, auth_user):
    _, u = auth_user
    own_app = _make_app(db_session, u)
    foreign_app = _other_users_app(db_session)

    # Create an interaction on the auth user's own app
    cr = client.post(
        f"/api/applications/{own_app.id}/interactions",
        json={"direction": "out", "channel": "mail", "body": "hi"},
    )
    assert cr.status_code in (200, 201), cr.text
    iid = cr.json()["interaction"]["id"]

    # Attempt to reassign to a foreign app — must be rejected
    pr = client.patch(
        f"/api/interactions/{iid}",
        json={"application_id": str(foreign_app.id)},
    )
    assert pr.status_code == 404, pr.text
