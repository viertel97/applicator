import uuid
from app.db.models import Application


def _make_app(db_session, user):
    a = Application(user_id=user.id, url="https://x.test/i", url_hash="hi")
    db_session.add(a); db_session.commit(); db_session.refresh(a)
    return a


def test_create_and_list(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u)
    payload = {
        "direction": "out", "channel": "linkedin",
        "body": "Pinged recruiter", "contact_name": "Anna",
    }
    r = client.post(f"/api/applications/{a.id}/interactions", json=payload)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["interaction"]["body"] == "Pinged recruiter"
    assert out["suggest_discard"] is None

    g = client.get(f"/api/applications/{a.id}/interactions")
    assert len(g.json()) == 1


def test_rejection_suggests_discard(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions",
        json={"direction": "in", "channel": "mail",
              "sentiment": "rejection", "body": "we regret..."},
    )
    out = r.json()
    assert out["suggest_discard"]["reason_slug"] == "rejected"
    assert out["suggest_discard"]["interaction_id"] == out["interaction"]["id"]


def test_outgoing_with_rejection_sentiment_no_suggest(client, db_session, auth_user):
    # rejection sentiment only meaningful for direction=in
    _, u = auth_user
    a = _make_app(db_session, u)
    r = client.post(
        f"/api/applications/{a.id}/interactions",
        json={"direction": "out", "channel": "mail",
              "sentiment": "rejection", "body": "I withdraw"},
    )
    assert r.json()["suggest_discard"] is None


def test_patch(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u)
    cr = client.post(
        f"/api/applications/{a.id}/interactions",
        json={"direction": "out", "channel": "mail", "body": "v1"},
    )
    iid = cr.json()["interaction"]["id"]
    pr = client.patch(f"/api/interactions/{iid}", json={"body": "v2"})
    assert pr.status_code == 200
    assert pr.json()["body"] == "v2"


def test_delete(client, db_session, auth_user):
    _, u = auth_user
    a = _make_app(db_session, u)
    cr = client.post(
        f"/api/applications/{a.id}/interactions",
        json={"direction": "out", "channel": "mail", "body": "x"},
    )
    iid = cr.json()["interaction"]["id"]
    dr = client.delete(f"/api/interactions/{iid}")
    assert dr.status_code == 204
    assert client.get(f"/api/applications/{a.id}/interactions").json() == []


def test_unowned_app_404(client):
    r = client.post(
        f"/api/applications/{uuid.uuid4()}/interactions",
        json={"direction": "out", "channel": "mail", "body": "x"},
    )
    assert r.status_code == 404
