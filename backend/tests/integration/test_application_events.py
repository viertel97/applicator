from app.db.models import (
    Application, ApplicationEvent, ApplicationEventKind, ApplicationStatus, User,
)


def test_status_change_writes_event(db_session, auth_user):
    _, user = auth_user
    app_row = Application(
        user_id=user.id, url="https://x.test/s", url_hash="hs",
        status=ApplicationStatus.draft,
    )
    db_session.add(app_row); db_session.commit()
    assert db_session.query(ApplicationEvent).filter_by(
        application_id=app_row.id, kind=ApplicationEventKind.status_change
    ).count() == 0

    app_row.status = ApplicationStatus.applied
    db_session.commit()

    evs = db_session.query(ApplicationEvent).filter_by(
        application_id=app_row.id, kind=ApplicationEventKind.status_change
    ).all()
    assert len(evs) == 1
    assert evs[0].from_value == "draft"
    assert evs[0].to_value == "applied"


def test_no_event_when_status_unchanged(db_session, auth_user):
    _, user = auth_user
    app_row = Application(
        user_id=user.id, url="https://x.test/n", url_hash="hn",
        status=ApplicationStatus.applied,
    )
    db_session.add(app_row); db_session.commit()
    before = db_session.query(ApplicationEvent).filter_by(
        application_id=app_row.id, kind=ApplicationEventKind.status_change,
    ).count()
    # touch a different column
    app_row.url = "https://x.test/n2"
    db_session.commit()
    after = db_session.query(ApplicationEvent).filter_by(
        application_id=app_row.id, kind=ApplicationEventKind.status_change,
    ).count()
    assert before == after


def test_fresh_insert_emits_no_status_change_event(db_session, auth_user):
    from app.db.models import (
        Application, ApplicationEvent, ApplicationEventKind, ApplicationStatus,
    )
    _, user = auth_user
    before = db_session.query(ApplicationEvent).filter_by(
        kind=ApplicationEventKind.status_change,
    ).count()
    a = Application(
        user_id=user.id, url="https://x.test/fresh", url_hash="hfresh",
        status=ApplicationStatus.applied,
    )
    db_session.add(a); db_session.commit()
    after = db_session.query(ApplicationEvent).filter_by(
        kind=ApplicationEventKind.status_change,
    ).count()
    assert after == before
