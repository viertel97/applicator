from app.db.models import (
    AnschreibenVariant,
    Application,
    ApplicationStatus,
    CVVariant,
    JobState,
    User,
)


def test_create_application(db_session, monkeypatch):
    monkeypatch.setenv("APP_SECRET_KEY", "x")
    u = User(ms_oid="o", email="a@b.c", display_name="A")
    db_session.add(u)
    db_session.flush()
    cv = CVVariant(user_id=u.id, name="default", source_md="cv", is_default=True)
    an = AnschreibenVariant(user_id=u.id, name="default", source_md="an", is_default=True)
    db_session.add_all([cv, an])
    db_session.flush()
    app = Application(
        user_id=u.id, url="http://x", url_hash="h",
        cv_variant_id=cv.id, anschreiben_variant_id=an.id,
    )
    db_session.add(app)
    db_session.commit()
    fetched = db_session.get(Application, app.id)
    assert fetched.status == ApplicationStatus.draft
    assert fetched.job_state == JobState.pending


def test_application_url_only_creation_persists(db_session):
    from app.db.models import (
        Application,
        FailedStage,
        JobState,
        User,
    )

    u = User(ms_oid="om", email="m@b.c", display_name="M")
    db_session.add(u)
    db_session.flush()
    app = Application(
        user_id=u.id,
        url="https://x.test/url-only",
        url_hash="h" * 64,
    )
    db_session.add(app)
    db_session.commit()
    db_session.refresh(app)

    assert app.cv_variant_id is None
    assert app.anschreiben_variant_id is None
    assert app.failed_stage is None
    assert app.job_posting_dirty is False
    assert app.job_state == JobState.pending


def test_jobstate_extracted_value_exists():
    from app.db.models import JobState

    assert JobState.extracted.value == "extracted"


def test_failed_stage_enum_values():
    from app.db.models import FailedStage

    assert {s.value for s in FailedStage} == {"crawl", "extract", "generate"}
