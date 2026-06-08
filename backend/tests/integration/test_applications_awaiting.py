from datetime import datetime, timedelta

from app.db.models import (
    Application, ApplicationStatus, Interaction, InteractionChannel,
    InteractionDirection,
)


def _app(db, user, slug, status=ApplicationStatus.applied):
    a = Application(user_id=user.id, url=f"https://x.test/{slug}",
                    url_hash=f"h{slug}", status=status)
    db.add(a)
    db.commit()
    return a


def _flag(client, aid):
    rows = client.get("/api/applications").json()
    return next(r for r in rows if r["id"] == str(aid))["awaiting_response"]


def test_outbound_latest_is_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "out")
    db_session.add(Interaction(application_id=a.id,
                               direction=InteractionDirection.out,
                               channel=InteractionChannel.mail))
    db_session.commit()
    assert _flag(client, a.id) is True


def test_inbound_latest_not_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "in")
    now = datetime.utcnow()
    db_session.add_all([
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    occurred_at=now - timedelta(days=2)),
        Interaction(application_id=a.id, direction=InteractionDirection.in_,
                    channel=InteractionChannel.mail,
                    occurred_at=now - timedelta(days=1)),
    ])
    db_session.commit()
    assert _flag(client, a.id) is False


def test_no_interactions_not_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "none")
    assert _flag(client, a.id) is False


def test_closed_status_not_awaiting(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "rej", status=ApplicationStatus.rejected)
    db_session.add(Interaction(application_id=a.id,
                               direction=InteractionDirection.out,
                               channel=InteractionChannel.mail))
    db_session.commit()
    assert _flag(client, a.id) is False


def test_get_app_carries_flag(client, db_session, auth_user):
    _, u = auth_user
    a = _app(db_session, u, "single")
    db_session.add(Interaction(application_id=a.id,
                               direction=InteractionDirection.out,
                               channel=InteractionChannel.mail))
    db_session.commit()
    body = client.get(f"/api/applications/{a.id}").json()
    assert body["awaiting_response"] is True
