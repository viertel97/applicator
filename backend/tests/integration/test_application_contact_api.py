from app.db.models import Application, JobPosting


def test_application_response_exposes_contact_block(auth_user, db_session):
    c, user = auth_user
    app_row = Application(
        user_id=user.id,
        url="https://x.test/contact",
        url_hash="c" * 64,
    )
    db_session.add(app_row)
    db_session.flush()
    jp = JobPosting(
        application_id=app_row.id,
        raw_text="raw",
        title="Dev",
        company="Acme",
        contact={"name": "Jane", "email": "j@x.com"},
    )
    db_session.add(jp)
    db_session.commit()

    r = c.get(f"/api/applications/{app_row.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    jp_body = body["job_posting"]
    assert jp_body is not None
    assert "contact" in jp_body
    assert jp_body["contact"]["name"] == "Jane"
    assert jp_body["contact"]["email"] == "j@x.com"
    assert "contact_person" not in jp_body
    assert "application_email" not in jp_body
