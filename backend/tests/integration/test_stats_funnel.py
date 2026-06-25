from app.db.models import (
    Application, ApplicationStatus, Interaction, InteractionChannel,
    InteractionDirection, InteractionSentiment,
)


def _seed(db, user):
    apps = []
    for i in range(3):
        a = Application(user_id=user.id, url=f"https://x.test/{i}", url_hash=f"h{i}",
                        status=ApplicationStatus.applied)
        db.add(a); apps.append(a)
    db.commit()
    return apps


def test_funnel_counts(client, db_session, auth_user):
    _, u = auth_user
    apps = _seed(db_session, u)
    r = client.get("/api/stats/funnel")
    body = r.json()
    assert body["totals"]["applications"] == 3
    stages = {s["stage"]: s["count"] for s in body["funnel"]}
    assert stages["created"] == 3
    assert stages["applied"] == 3
    assert stages["responded"] == 0


def test_cross_channel_response_not_counted(client, db_session, auth_user):
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/c", url_hash="hc",
                    status=ApplicationStatus.applied)
    db_session.add(a); db_session.commit()
    db_session.add_all([
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail),
        Interaction(application_id=a.id, direction=InteractionDirection.in_,
                    channel=InteractionChannel.linkedin),
    ])
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    rates = {r["channel"]: r for r in body["response_rate_by_channel"]}
    assert rates.get("mail", {}).get("responses", 0) == 0
    assert rates.get("linkedin", {}).get("responses", 0) == 0
    # funnel responded counts the in interaction regardless of channel
    stages = {s["stage"]: s["count"] for s in body["funnel"]}
    assert stages["responded"] == 1


def test_same_channel_response_counted(client, db_session, auth_user):
    from datetime import datetime, timedelta
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/m", url_hash="hm",
                    status=ApplicationStatus.applied)
    db_session.add(a); db_session.commit()
    now = datetime.utcnow()
    db_session.add_all([
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    occurred_at=now - timedelta(days=2)),
        Interaction(application_id=a.id, direction=InteractionDirection.in_,
                    channel=InteractionChannel.mail,
                    occurred_at=now - timedelta(days=1)),
    ])
    db_session.commit()
    rates = {r["channel"]: r for r in
             client.get("/api/stats/funnel").json()["response_rate_by_channel"]}
    assert rates["mail"]["responses"] == 1
    assert rates["mail"]["outgoing"] == 1


def test_discard_breakdown(client, db_session, auth_user):
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/db", url_hash="hd",
                    status=ApplicationStatus.discarded)
    db_session.add(a); db_session.commit()
    rejected = next(r for r in client.get("/api/discard-reasons").json()
                    if r["slug"] == "rejected")
    db_session.execute(
        __import__("sqlalchemy").text(
            "UPDATE application SET discard_reason_id = :r WHERE id = :a"
        ),
        {"r": rejected["id"], "a": str(a.id)},
    )
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    breakdown = {x["slug"]: x for x in body["discard_breakdown"]}
    assert breakdown["rejected"]["count"] == 1


def test_applied_excludes_pre_apply_and_discarded(client, db_session, auth_user):
    from app.db.models import ApplicationStatus
    _, u = auth_user
    for i, st in enumerate([
        ApplicationStatus.need_call,
        ApplicationStatus.apply_direct,
        ApplicationStatus.discarded,
        ApplicationStatus.draft,
    ]):
        db_session.add(Application(
            user_id=u.id, url=f"https://x.test/p{i}", url_hash=f"hp{i}", status=st,
        ))
    db_session.add(Application(
        user_id=u.id, url="https://x.test/ap", url_hash="hap",
        status=ApplicationStatus.applied,
    ))
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    # only the one applied app counts
    assert body["totals"]["applied"] == 1
    stages = {s["stage"]: s["count"] for s in body["funnel"]}
    assert stages["applied"] == 1
    total_weekly_applied = sum(w["applied"] for w in body["weekly_volume"])
    total_weekly_discarded = sum(w["discarded"] for w in body["weekly_volume"])
    assert total_weekly_applied == 1
    assert total_weekly_discarded == 1  # discarded not also counted as applied


def test_interview_status_counts_in_applied_and_funnel(client, db_session, auth_user):
    _, u = auth_user
    a = Application(
        user_id=u.id, url="https://x.test/iv", url_hash="hiv",
        status=ApplicationStatus.interview,
    )
    db_session.add(a)
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    stages = {s["stage"]: s["count"] for s in body["funnel"]}
    assert stages["interview"] == 1, "interview-status app must appear in interview funnel stage"
    assert body["totals"]["applied"] == 1, "interview-status app must count in totals.applied"
    assert stages["applied"] == 1, "interview-status app must count in applied funnel stage"


def test_interview_status_no_double_count(client, db_session, auth_user):
    """An app with both status=interview and an interview Interaction counts once."""
    _, u = auth_user
    a = Application(
        user_id=u.id, url="https://x.test/iv2", url_hash="hiv2",
        status=ApplicationStatus.interview,
    )
    db_session.add(a)
    db_session.commit()
    db_session.add(Interaction(
        application_id=a.id,
        direction=InteractionDirection.out,
        channel=InteractionChannel.interview,
    ))
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    stages = {s["stage"]: s["count"] for s in body["funnel"]}
    assert stages["interview"] == 1, "app with both status and interaction must count only once"


def test_weekly_inquiries_counted(client, db_session, auth_user):
    from app.db.models import (
        ApplicationStatus, Interaction, InteractionChannel,
        InteractionCreatedFrom, InteractionDirection,
    )
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/wi", url_hash="hwi",
                    status=ApplicationStatus.need_call)
    db_session.add(a); db_session.commit(); db_session.refresh(a)
    db_session.add_all([
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    created_from=InteractionCreatedFrom.inquiry_sent),
        Interaction(application_id=a.id, direction=InteractionDirection.out,
                    channel=InteractionChannel.mail,
                    created_from=InteractionCreatedFrom.manual),
    ])
    db_session.commit()
    body = client.get("/api/stats/funnel").json()
    total_inquiries = sum(w["inquiries"] for w in body["weekly_volume"])
    assert total_inquiries == 1  # only the inquiry_sent one
    # need_call app is not an application
    assert body["totals"]["applied"] == 0
