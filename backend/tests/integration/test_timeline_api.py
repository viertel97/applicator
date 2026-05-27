def test_timeline_merges_three_sources(client, db_session, auth_user):
    from app.db.models import Application, Interview, InterviewKind
    _, user = auth_user
    a = Application(user_id=user.id, url="https://x.test/t", url_hash="ht")
    db_session.add(a); db_session.commit()
    aid = a.id

    # status change -> auto event
    client.patch(f"/api/applications/{aid}", json={"status": "applied"})
    # interaction
    client.post(f"/api/applications/{aid}/interactions",
                json={"direction": "out", "channel": "mail",
                      "subject": "Hi", "body": "..."})
    # interview
    db_session.add(Interview(application_id=aid, kind=InterviewKind.phone,
                             scheduled_at="2026-06-01T10:00:00"))
    db_session.commit()

    r = client.get(f"/api/applications/{aid}/timeline")
    assert r.status_code == 200
    body = r.json()
    kinds = [row["kind"] for row in body]
    assert "interaction" in kinds and "interview" in kinds and "event" in kinds
    # newest first
    ts = [row["at"] for row in body]
    assert ts == sorted(ts, reverse=True)
