from app.db.models import Application, Interaction, InteractionCreatedFrom


def test_mark_sent_tags_interaction_as_inquiry_sent(client, db_session, auth_user):
    _, u = auth_user
    a = Application(user_id=u.id, url="https://x.test/inq", url_hash="hinq")
    db_session.add(a)
    db_session.commit()
    db_session.refresh(a)

    r = client.post(
        f"/api/applications/{a.id}/inquiry/mark-sent",
        json={"subject": "Frage", "body": "Hallo"},
    )
    assert r.status_code == 200

    it = db_session.query(Interaction).filter_by(application_id=a.id).one()
    assert it.created_from == InteractionCreatedFrom.inquiry_sent
    assert it.direction.value == "out"
    assert it.channel.value == "mail"
