from app.db.models import (
    AnschreibenVariant,
    Application,
    ApplicationStatus,
    CVVariant,
    JobState,
)


def _make_app(db_session, user):
    cv = db_session.query(CVVariant).filter_by(user_id=user.id).first()
    an = db_session.query(AnschreibenVariant).filter_by(user_id=user.id).first()
    app_row = Application(
        user_id=user.id,
        url="https://x.test/iv",
        url_hash="h-iv",
        cv_variant_id=cv.id,
        anschreiben_variant_id=an.id,
        status=ApplicationStatus.draft,
        job_state=JobState.ready,
    )
    db_session.add(app_row)
    db_session.commit()
    db_session.refresh(app_row)
    return app_row


def test_interview_lifecycle(auth_user, db_session):
    c, u = auth_user
    app_row = _make_app(db_session, u)

    r = c.post(
        f"/api/applications/{app_row.id}/interviews",
        json={"scheduled_at": "2026-05-10T10:00:00", "kind": "phone", "notes": "n1"},
    )
    assert r.status_code == 200, r.text
    iid = r.json()["id"]

    r2 = c.post(
        f"/api/applications/{app_row.id}/interviews",
        json={"scheduled_at": "2026-05-12T10:00:00", "kind": "technical"},
    )
    assert r2.status_code == 200

    r3 = c.get(f"/api/applications/{app_row.id}/interviews")
    assert r3.status_code == 200
    assert len(r3.json()) == 2

    r4 = c.patch(f"/api/interviews/{iid}", json={"outcome": "passed", "notes": "ok"})
    assert r4.status_code == 200, r4.text
    assert r4.json()["outcome"] == "passed"
    assert r4.json()["notes"] == "ok"

    r5 = c.delete(f"/api/interviews/{iid}")
    assert r5.status_code == 200
    assert len(c.get(f"/api/applications/{app_row.id}/interviews").json()) == 1


def test_interview_404_unowned_app(auth_user):
    c, _ = auth_user
    import uuid
    fake_aid = uuid.uuid4()
    r = c.post(
        f"/api/applications/{fake_aid}/interviews",
        json={"scheduled_at": "2026-05-10T10:00:00", "kind": "phone"},
    )
    assert r.status_code == 404


def test_interview_patch_404(auth_user):
    c, _ = auth_user
    import uuid
    r = c.patch(f"/api/interviews/{uuid.uuid4()}", json={"outcome": "passed"})
    assert r.status_code == 404
