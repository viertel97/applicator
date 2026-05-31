from app.email_ingest.models import ParsedMessage, ParsedThread


def test_parsed_message_defaults():
    m = ParsedMessage()
    assert m.sender_name is None
    assert m.sender_email is None
    assert m.recipients == []
    assert m.occurred_at is None
    assert m.subject is None
    assert m.body == ""


def test_parsed_thread_holds_messages():
    t = ParsedThread(messages=[ParsedMessage(body="hi")])
    assert len(t.messages) == 1
    assert t.messages[0].body == "hi"
    assert t.used_llm is False
