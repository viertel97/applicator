import json

from app.email_ingest.llm_split import LlmThread, llm_split_thread
from tests.fakes.llm import FakeLLM


def _canned(_messages, _schema):
    return json.dumps(
        {
            "messages": [
                {
                    "sender_name": "Anna",
                    "sender_email": "anna@acme.test",
                    "recipients": ["me@self.test"],
                    "date_text": "Apr 30 2026 16:00",
                    "subject": "Re: Your application",
                    "body": "newest message",
                },
                {
                    "sender_name": "Me",
                    "sender_email": "me@self.test",
                    "recipients": ["anna@acme.test"],
                    "date_text": "Apr 30 2026 13:00",
                    "subject": "Your application",
                    "body": "older message",
                },
            ]
        }
    )


def test_llm_split_returns_parsed_messages():
    llm = FakeLLM(handler=_canned)
    msgs = llm_split_thread("some messy thread text", llm)
    assert len(msgs) == 2
    assert msgs[0].sender_email == "anna@acme.test"
    assert msgs[0].body == "newest message"
    # date_text parsed into occurred_at
    assert msgs[0].occurred_at is not None
    assert msgs[0].occurred_at.year == 2026
    # llm was asked for JSON schema
    assert llm.calls[0][1] is not None  # json_schema passed


def test_llm_schema_has_messages_array():
    schema = LlmThread.model_json_schema()
    assert "messages" in schema["properties"]
