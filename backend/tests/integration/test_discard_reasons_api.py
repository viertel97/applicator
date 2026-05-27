import sqlalchemy as sa


def test_list_seeds_on_first_call(client):
    r = client.get("/api/discard-reasons")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 10
    assert any(item["slug"] == "no_reply" for item in body)
    assert all("usage_count" in item for item in body)


def test_list_idempotent_no_duplicate_seed(client):
    r1 = client.get("/api/discard-reasons").json()
    r2 = client.get("/api/discard-reasons").json()
    assert len(r1) == len(r2) == 10


def test_create_auto_slug(client):
    r = client.post("/api/discard-reasons", json={"label": "Hiring frozen"})
    assert r.status_code == 200
    assert r.json()["slug"] == "hiring_frozen"
    assert r.json()["is_system"] is False


def test_create_collision(client):
    client.post("/api/discard-reasons", json={"label": "Custom"})
    r = client.post("/api/discard-reasons", json={"label": "Custom"})
    assert r.status_code == 200
    assert r.json()["slug"] == "custom_2"


def test_patch_label_immutable_slug(client):
    seed = client.get("/api/discard-reasons").json()
    rid = next(x for x in seed if x["slug"] == "no_reply")["id"]
    r = client.patch(
        f"/api/discard-reasons/{rid}",
        json={"label": "Ghosted", "slug": "ghosted"},
    )
    assert r.status_code == 200
    assert r.json()["slug"] == "no_reply"
    assert r.json()["label"] == "Ghosted"


def test_archive_then_list_excludes(client):
    seed = client.get("/api/discard-reasons").json()
    rid = next(x for x in seed if x["slug"] == "duplicate")["id"]
    client.patch(f"/api/discard-reasons/{rid}", json={"is_archived": True})
    visible = client.get("/api/discard-reasons").json()
    assert all(row["id"] != rid for row in visible)
    with_arch = client.get("/api/discard-reasons?include_archived=1").json()
    assert any(row["id"] == rid for row in with_arch)


def test_delete_409_when_referenced(client, db_session, auth_user):
    from app.db.models import Application
    _, user = auth_user
    seed = client.get("/api/discard-reasons").json()
    rid = next(x for x in seed if x["slug"] == "rejected")["id"]
    app_row = Application(user_id=user.id, url="https://x.test/r", url_hash="hr")
    db_session.add(app_row)
    db_session.commit()
    db_session.execute(
        sa.text(
            "UPDATE application SET discard_reason_id = :r WHERE id = :a"
        ),
        {"r": rid, "a": str(app_row.id)},
    )
    db_session.commit()
    r = client.delete(f"/api/discard-reasons/{rid}")
    assert r.status_code == 409


def test_delete_ok_when_unused(client):
    r1 = client.post("/api/discard-reasons", json={"label": "Disposable"})
    rid = r1.json()["id"]
    r = client.delete(f"/api/discard-reasons/{rid}")
    assert r.status_code == 204


def test_patch_rejects_empty_label(client):
    seed = client.get("/api/discard-reasons").json()
    rid = next(x for x in seed if x["slug"] == "no_reply")["id"]
    r = client.patch(f"/api/discard-reasons/{rid}", json={"label": "   "})
    assert r.status_code == 400
