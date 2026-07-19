def test_global_timeline_aggregates_and_scopes(client, db_session, auth_user):
    from app.db.models import Application, JobPosting

    _, user = auth_user

    # App A: gets a job posting + status change to applied + an interaction
    a = Application(user_id=user.id, url="https://x.test/a", url_hash="ha")
    db_session.add(a)
    db_session.commit()
    db_session.add(
        JobPosting(application_id=a.id, raw_text="jd", company="Acme", title="Engineer")
    )
    db_session.commit()
    aid = a.id

    client.patch(f"/api/applications/{aid}", json={"status": "applied"})
    client.post(
        f"/api/applications/{aid}/interactions",
        json={"direction": "out", "channel": "mail", "subject": "Hi"},
    )
    client.patch(f"/api/applications/{aid}", json={"status": "interview"})
    client.patch(f"/api/applications/{aid}", json={"status": "rejected"})

    # App B: only created, never touched
    b = Application(user_id=user.id, url="https://x.test/b", url_hash="hb")
    db_session.add(b)
    db_session.commit()

    r = client.get("/api/timeline")
    assert r.status_code == 200
    rows = r.json()

    cats = [row["category"] for row in rows]
    assert cats.count("application") == 2          # one per app
    assert "interaction" in cats
    assert "applied" in cats                       # draft -> applied (submission)
    assert "status" in cats                        # applied -> interview
    assert "discard" in cats                       # interview -> rejected

    # company/title enrichment present on App A rows
    acme_rows = [row for row in rows if row["application_id"] == str(aid)]
    assert all(row["company"] == "Acme" for row in acme_rows)
    assert all(row["title"] == "Engineer" for row in acme_rows)

    # interaction data payload
    interaction_row = next(row for row in rows if row["category"] == "interaction")
    assert interaction_row["data"]["direction"] == "out"
    assert interaction_row["data"]["channel"] == "mail"
    assert interaction_row["data"]["subject"] == "Hi"

    # status/discard event data payload has non-null from/to
    discard_row = next(row for row in rows if row["category"] == "discard")
    assert discard_row["data"]["to"] == "rejected"
    assert discard_row["data"]["from"] is not None
    status_row = next(row for row in rows if row["category"] == "status")
    assert status_row["data"]["from"] is not None
    assert status_row["data"]["to"] is not None

    # draft -> applied is its own "applied" (submission) category
    applied_rows = [row for row in rows if row["category"] == "applied"]
    assert any(row["data"]["to"] == "applied" for row in applied_rows)
    # the applied transition must NOT be miscategorized as status or discard
    status_tos = [row["data"]["to"] for row in rows if row["category"] == "status"]
    discard_tos = [row["data"]["to"] for row in rows if row["category"] == "discard"]
    assert "applied" not in status_tos
    assert "applied" not in discard_tos

    # newest first
    ts = [row["at"] for row in rows]
    assert ts == sorted(ts, reverse=True)


def test_global_timeline_excludes_other_users(client, db_session, auth_user):
    from app.db.models import Application, User

    _, user = auth_user
    other = User(ms_oid="other", email="other@b.c", display_name="O")
    db_session.add(other)
    db_session.flush()
    db_session.add(Application(user_id=other.id, url="https://x.test/o", url_hash="ho"))
    db_session.commit()

    r = client.get("/api/timeline")
    assert r.status_code == 200
    assert r.json() == []


def test_global_timeline_excludes_deleted_apps(client, db_session, auth_user):
    from datetime import datetime, timezone
    from app.db.models import Application

    _, user = auth_user
    a = Application(
        user_id=user.id, url="https://x.test/d", url_hash="hd",
        deleted_at=datetime.now(timezone.utc),
    )
    db_session.add(a)
    db_session.commit()

    r = client.get("/api/timeline")
    assert r.status_code == 200
    assert r.json() == []
