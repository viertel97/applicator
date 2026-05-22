def test_get_labels_returns_category(client, db_session):
    from app.db.models import Label, LabelCategory
    db_session.add(Label(name="Python", color="#fff", category=LabelCategory.tech))
    db_session.commit()
    r = client.get("/api/labels")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["category"] == "tech"


def test_create_label_requires_category(client):
    r = client.post("/api/labels", json={"name": "X", "color": "#fff"})
    assert r.status_code == 422


def test_create_label_with_category(client, db_session):
    r = client.post(
        "/api/labels",
        json={"name": "Custom", "color": "#fff", "category": "other"},
    )
    assert r.status_code == 201
    assert r.json()["category"] == "other"


def test_patch_label_updates_category(client, db_session):
    from app.db.models import Label, LabelCategory
    lab = Label(name="OldName", color="#fff", category=LabelCategory.other)
    db_session.add(lab)
    db_session.commit()

    r = client.patch(
        f"/api/labels/{lab.id}",
        json={"category": "tech", "name": "NewName"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["category"] == "tech"
    assert body["name"] == "NewName"


def test_get_labels_sorted_by_category_then_name(client, db_session):
    from app.db.models import Label, LabelCategory
    db_session.add_all([
        Label(name="Python", color="#fff", category=LabelCategory.tech),
        Label(name="AWS", color="#fff", category=LabelCategory.tech),
        Label(name="Senior", color="#fff", category=LabelCategory.seniority),
    ])
    db_session.commit()
    r = client.get("/api/labels")
    names = [(l["category"], l["name"]) for l in r.json()]
    assert names == [
        ("seniority", "Senior"),
        ("tech", "AWS"),
        ("tech", "Python"),
    ]
