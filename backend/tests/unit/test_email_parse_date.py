from datetime import datetime

from app.email_ingest.llm_split import _parse_date


def test_full_date_with_year_is_kept():
    dt = _parse_date("Dienstag, 10. September 2024 22:06")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2024, 9, 10)
    assert (dt.hour, dt.minute) == (22, 6)


def test_yearless_german_date_does_not_land_in_future():
    # "10. August 22:06" has no year; dateutil used to default to the
    # current year and produce a future date. It must stay in the past.
    dt = _parse_date("Mittwoch, 10. August 22:06")
    assert dt is not None
    assert dt <= datetime.now(dt.tzinfo)
    assert (dt.month, dt.day, dt.hour, dt.minute) == (8, 10, 22, 6)


def test_yearless_english_date_does_not_land_in_future():
    dt = _parse_date("September 10, 22:06")
    assert dt is not None
    assert dt <= datetime.now(dt.tzinfo)
    assert (dt.month, dt.day) == (9, 10)


def test_german_numeric_dayfirst():
    dt = _parse_date("30.04.2026 um 16:00")
    assert dt is not None
    assert (dt.year, dt.month, dt.day) == (2026, 4, 30)


def test_empty_returns_none():
    assert _parse_date("") is None
    assert _parse_date("   ") is None
