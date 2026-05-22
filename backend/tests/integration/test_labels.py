def test_list_labels_empty(auth_user):
    client, _ = auth_user
    r = client.get("/api/labels")
    assert r.status_code == 200
    assert r.json() == []


def test_create_label(auth_user):
    client, _ = auth_user
    r = client.post("/api/labels", json={"name": "Startup", "color": "#6366f1", "category": "other"})
    assert r.status_code == 201
    data = r.json()
    assert data["name"] == "Startup"
    assert data["color"] == "#6366f1"
    assert data["is_auto"] is False
    assert "id" in data


def test_create_duplicate_label_returns_409(auth_user):
    client, _ = auth_user
    client.post("/api/labels", json={"name": "Tech", "color": "#3b82f6", "category": "tech"})
    r = client.post("/api/labels", json={"name": "Tech", "color": "#ef4444", "category": "tech"})
    assert r.status_code == 409


def test_assign_and_list_label_on_application(auth_user, no_celery):
    client, _ = auth_user

    label_r = client.post("/api/labels", json={"name": "Finance", "color": "#f59e0b", "category": "other"})
    label_id = label_r.json()["id"]

    app_r = client.post("/api/applications", json={"url": "https://example.com/job/label-test"})
    assert app_r.status_code == 202
    app_id = app_r.json()["id"]

    r = client.post(f"/api/applications/{app_id}/labels/{label_id}")
    assert r.status_code == 200
    data = r.json()
    assert any(lbl["id"] == label_id for lbl in data["labels"])


def test_remove_label_from_application(auth_user, no_celery):
    client, _ = auth_user

    label_r = client.post("/api/labels", json={"name": "Remote", "color": "#10b981", "category": "work_mode"})
    label_id = label_r.json()["id"]

    app_r = client.post("/api/applications", json={"url": "https://example.com/job/remove-test"})
    app_id = app_r.json()["id"]

    client.post(f"/api/applications/{app_id}/labels/{label_id}")
    r = client.delete(f"/api/applications/{app_id}/labels/{label_id}")
    assert r.status_code == 200
    assert not any(lbl["id"] == label_id for lbl in r.json()["labels"])


def test_filter_applications_by_label(auth_user, no_celery):
    client, _ = auth_user

    label_r = client.post("/api/labels", json={"name": "Agency", "color": "#8b5cf6", "category": "other"})
    label_id = label_r.json()["id"]

    r1 = client.post("/api/applications", json={"url": "https://example.com/job/filter-a"})
    app1_id = r1.json()["id"]
    r2 = client.post("/api/applications", json={"url": "https://example.com/job/filter-b"})
    app2_id = r2.json()["id"]

    client.post(f"/api/applications/{app1_id}/labels/{label_id}")

    r = client.get(f"/api/applications?label_ids={label_id}")
    assert r.status_code == 200
    ids = [a["id"] for a in r.json()]
    assert app1_id in ids
    assert app2_id not in ids


def test_applications_list_includes_labels(auth_user):
    client, _ = auth_user
    r = client.get("/api/applications")
    assert r.status_code == 200
    for a in r.json():
        assert "labels" in a
        assert "posting_online" in a
