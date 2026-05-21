import uuid


def test_delete_application_sets_deleted_at(client, sample_application):
    aid = sample_application
    r = client.delete(f"/api/applications/{aid}")
    assert r.status_code == 204


def test_deleted_application_excluded_from_list(client, sample_application):
    aid = sample_application
    client.delete(f"/api/applications/{aid}")
    r = client.get("/api/applications")
    ids = [a["id"] for a in r.json()]
    assert aid not in ids


def test_deleted_application_get_returns_404(client, sample_application):
    aid = sample_application
    client.delete(f"/api/applications/{aid}")
    r = client.get(f"/api/applications/{aid}")
    assert r.status_code == 404


def test_delete_is_idempotent(client, sample_application):
    aid = sample_application
    client.delete(f"/api/applications/{aid}")
    r = client.delete(f"/api/applications/{aid}")
    assert r.status_code == 204


def test_delete_unknown_id_returns_404(client):
    r = client.delete(f"/api/applications/{uuid.uuid4()}")
    assert r.status_code == 404
