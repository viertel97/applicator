from app.email_ingest.confidence import Confidence, score
from app.email_ingest.models import ParsedMessage


def _msg(**kw):
    return ParsedMessage(**kw)


def test_markers_present_but_no_segments_is_low():
    # body mentions a quote marker but split produced only the top message
    det = [_msg(sender_email="a@b.c", body="On Wed wrote: see below")]
    body = "Some text\nOn Wed, Apr 30, 2026 someone wrote:\nold stuff"
    assert score(det, body) == Confidence.LOW


def test_clean_multi_segment_is_high():
    det = [
        _msg(sender_email="a@b.c", occurred_at=None, body="new"),
        _msg(sender_email="x@y.z", body="old"),
    ]
    body = "new\nFrom: X\nold"
    assert score(det, body) == Confidence.HIGH


def test_unknown_sender_and_unparseable_date_is_low():
    from datetime import datetime

    det = [
        _msg(sender_email="a@b.c", occurred_at=datetime.now(), body="new"),
        _msg(sender_email=None, occurred_at=None, body="old"),
    ]
    body = "new\nFrom: ?\nold"
    assert score(det, body) == Confidence.LOW


def test_single_message_no_markers_is_high():
    det = [_msg(sender_email="a@b.c", body="just one message")]
    assert score(det, "just one message") == Confidence.HIGH
