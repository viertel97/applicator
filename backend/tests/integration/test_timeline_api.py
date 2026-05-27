def test_timeline_merges_interactions_and_events(client, db_session, auth_user):
    from app.db.models import Application
    _, user = auth_user
    a = Application(user_id=user.id, url="https://x.test/t", url_hash="ht")
    db_session.add(a); db_session.commit()
    aid = a.id

    # status change -> auto event
    client.patch(f"/api/applications/{aid}", json={"status": "applied"})
    # outgoing mail interaction
    client.post(f"/api/applications/{aid}/interactions",
                json={"direction": "out", "channel": "mail",
                      "subject": "Hi", "body": "..."})
    # interview logged as interaction
    client.post(f"/api/applications/{aid}/interactions",
                json={"direction": "out", "channel": "interview",
                      "body": "Went well"})

    r = client.get(f"/api/applications/{aid}/timeline")
    assert r.status_code == 200
    body = r.json()
    kinds = {row["kind"] for row in body}
    assert kinds == {"interaction", "event"}
    channels = {row["data"].get("channel") for row in body if row["kind"] == "interaction"}
    assert "interview" in channels
    # newest first
    ts = [row["at"] for row in body]
    assert ts == sorted(ts, reverse=True)
