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


def test_timeline_interaction_carries_edit_fields(client, db_session, auth_user):
    """The edit-interview modal reads these off row.data; missing occurred_at
    made new Date(undefined).toISOString() throw RangeError on render."""
    from app.db.models import Application
    _, user = auth_user
    a = Application(user_id=user.id, url="https://x.test/e", url_hash="he")
    db_session.add(a); db_session.commit()
    aid = a.id

    client.post(f"/api/applications/{aid}/interactions",
                json={"direction": "out", "channel": "interview",
                      "body": "Onsite", "location": "HQ"})

    r = client.get(f"/api/applications/{aid}/timeline")
    assert r.status_code == 200
    iv = next(row for row in r.json()
              if row["kind"] == "interaction" and row["data"].get("channel") == "interview")
    for field in ("occurred_at", "application_id", "ends_at", "location"):
        assert field in iv["data"], f"timeline data missing {field}"
    assert iv["data"]["occurred_at"]  # non-empty, parseable by JS Date
