def test_preview_requires_auth(app_client):
    r = app_client.post("/api/settings/inquiry-prompt/preview", json={"source_md": "x"})
    assert r.status_code == 401


def test_preview_returns_both_languages(auth_user):
    client, _ = auth_user
    r = client.post("/api/settings/inquiry-prompt/preview", json={"source_md": "SYS"})
    assert r.status_code == 200
    data = r.json()
    assert set(data) == {"de", "en"}
    assert data["de"]["system_prompt"] == "SYS"
    assert data["de"]["greeting"] in data["de"]["email"]
    assert len(data["de"]["questions"]) == 2


def test_preview_reflects_custom_body_template(auth_user):
    client, _ = auth_user
    r = client.post(
        "/api/settings/inquiry-prompt/preview",
        json={"source_md": "SYS", "body_template_de": "DE::{greeting}"},
    )
    assert r.status_code == 200
    assert r.json()["de"]["email"] == "DE::Sehr geehrte Frau Müller"


def test_preview_tolerates_malformed_user_prompt_template(auth_user):
    client, _ = auth_user
    r = client.post(
        "/api/settings/inquiry-prompt/preview",
        json={"source_md": "SYS", "user_prompt_md": "{title} {oops} {0} {"},
    )
    assert r.status_code == 200
    assert r.json()["de"]["user_prompt"] == "Data Engineer {oops} {0} {"


def test_preview_does_not_write_db(auth_user, db_session):
    from app.db.models import InquiryPromptTemplate

    client, _ = auth_user
    before = db_session.query(InquiryPromptTemplate).count()
    client.post("/api/settings/inquiry-prompt/preview", json={"source_md": "SYS"})
    after = db_session.query(InquiryPromptTemplate).count()
    assert before == after == 0
