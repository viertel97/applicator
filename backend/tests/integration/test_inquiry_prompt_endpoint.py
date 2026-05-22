from app.inquiry.prompts import DEFAULT_TEMPLATE


def test_get_seeds_default_on_first_call(auth_user):
    client, _ = auth_user
    r = client.get("/api/settings/inquiry-prompt")
    assert r.status_code == 200
    assert r.json()["source_md"] == DEFAULT_TEMPLATE


def test_put_updates_source_md(auth_user):
    client, _ = auth_user
    client.get("/api/settings/inquiry-prompt")
    r = client.put(
        "/api/settings/inquiry-prompt",
        json={"source_md": "custom prompt"},
    )
    assert r.status_code == 200
    assert r.json()["source_md"] == "custom prompt"

    again = client.get("/api/settings/inquiry-prompt")
    assert again.json()["source_md"] == "custom prompt"


def test_get_requires_auth(app_client):
    r = app_client.get("/api/settings/inquiry-prompt")
    assert r.status_code == 401
