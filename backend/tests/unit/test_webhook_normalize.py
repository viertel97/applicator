from app.api.webhooks import InboundEmail


def test_normalize_plain_string_from():
    e = InboundEmail.normalize({"from": "jane@acme.example", "subject": "Hi"})
    assert e.from_ == "jane@acme.example"
    assert e.subject == "Hi"


def test_normalize_object_from_picks_email():
    e = InboundEmail.normalize(
        {"from": {"email": "onboarding@inboxbridge.io", "name": "Bridge"},
         "subject": "Welcome"}
    )
    assert e.from_ == "onboarding@inboxbridge.io"
    assert e.subject == "Welcome"


def test_normalize_object_from_falls_back_to_sender():
    e = InboundEmail.normalize({"sender": {"address": "a@b.c"}})
    assert e.from_ == "a@b.c"


def test_normalize_empty_object_from_yields_empty_string():
    e = InboundEmail.normalize({"from": {"email": "", "name": ""}})
    assert e.from_ == ""
