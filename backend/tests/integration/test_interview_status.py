"""Integration tests for the 'interview' ApplicationStatus value.

Verifies PATCH /api/applications/{id} accepts 'interview', that the returned
status is 'interview', and that the app is still counted as active (open).
"""
from app.db.models import Application, ApplicationStatus


def test_patch_status_to_interview(client, db_session, auth_user, sample_application):
    app_id = sample_application
    r = client.patch(f"/api/applications/{app_id}", json={"status": "interview"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "interview"


def test_interview_app_is_active(client, db_session, auth_user):
    """An interview app must NOT appear in closed statuses — totals.active counts it."""
    _, u = auth_user
    interview_app = Application(
        user_id=u.id, url="https://x.test/act1", url_hash="hact1",
        status=ApplicationStatus.interview,
    )
    accepted_app = Application(
        user_id=u.id, url="https://x.test/act2", url_hash="hact2",
        status=ApplicationStatus.accepted,
    )
    db_session.add_all([interview_app, accepted_app])
    db_session.commit()

    body = client.get("/api/stats/funnel").json()
    # interview is open; accepted is closed
    assert body["totals"]["active"] == 1, (
        "interview app should be active; accepted app should not"
    )
