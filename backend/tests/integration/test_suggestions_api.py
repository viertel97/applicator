from datetime import datetime, timezone

from app.db.models import Application, ApplicationStatus, JobPosting, User


def _draft(db, user, slug, *, online=None, reason=None, dismissed=None,
           status=ApplicationStatus.draft):
    a = Application(
        user_id=user.id,
        url=f"https://x.test/{slug}",
        url_hash=f"h{slug}",
        status=status,
        posting_online=online,
        posting_offline_reason=reason,
        posting_offline_dismissed_at=dismissed,
        posting_checked_at=datetime.now(timezone.utc),
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _ids(client):
    return {r["id"] for r in client.get("/api/applications/suggestions").json()}


def test_suggestions_lists_only_offline_nondismissed_drafts(client, db_session, auth_user):
    _, u = auth_user
    offline = _draft(db_session, u, "offline", online=False, reason="http_404")
    _draft(db_session, u, "online", online=True)
    _draft(db_session, u, "unknown", online=None)
    _draft(db_session, u, "dismissed", online=False, reason="http_404",
           dismissed=datetime.now(timezone.utc))
    _draft(db_session, u, "applied-offline", online=False, reason="http_404",
           status=ApplicationStatus.applied)

    assert _ids(client) == {str(offline.id)}


def test_suggestion_payload_includes_title_company_reason(client, db_session, auth_user):
    _, u = auth_user
    a = _draft(db_session, u, "withpost", online=False, reason="redirect_root")
    db_session.add(JobPosting(application_id=a.id, raw_text="x",
                              title="Backend Engineer", company="Acme"))
    db_session.commit()

    item = client.get("/api/applications/suggestions").json()[0]
    assert item["title"] == "Backend Engineer"
    assert item["company"] == "Acme"
    assert item["posting_offline_reason"] == "redirect_root"
    assert item["posting_checked_at"] is not None


def test_dismiss_removes_from_suggestions(client, db_session, auth_user):
    _, u = auth_user
    a = _draft(db_session, u, "d1", online=False, reason="http_403")
    assert _ids(client) == {str(a.id)}

    r = client.post(f"/api/applications/{a.id}/dismiss-offline")
    assert r.status_code == 200
    assert _ids(client) == set()


def test_dismiss_is_idempotent(client, db_session, auth_user):
    _, u = auth_user
    a = _draft(db_session, u, "d2", online=False, reason="http_403")
    first = client.post(f"/api/applications/{a.id}/dismiss-offline").json()
    second = client.post(f"/api/applications/{a.id}/dismiss-offline").json()
    assert first["id"] == second["id"] == str(a.id)
    assert _ids(client) == set()


def test_dismiss_other_users_app_is_404(client, db_session, auth_user):
    _, u = auth_user
    other = User(ms_oid="o2", email="x@y.z", display_name="B")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    a = _draft(db_session, other, "foreign", online=False, reason="http_404")

    r = client.post(f"/api/applications/{a.id}/dismiss-offline")
    assert r.status_code == 404
