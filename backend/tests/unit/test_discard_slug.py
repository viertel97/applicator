from app.api.discard_reasons import _derive_slug, _unique_slug


def test_basic_slug():
    assert _derive_slug("No reply") == "no_reply"
    assert _derive_slug("Salary too low") == "salary_too_low"


def test_collapses_whitespace_and_punct():
    assert _derive_slug("a  b   c") == "a_b_c"
    assert _derive_slug("Hi!  Test 123") == "hi_test_123"


def test_truncate_to_64():
    long = "x" * 200
    assert len(_derive_slug(long)) <= 64


def test_empty_fallback():
    assert _derive_slug("???") == "reason"
    assert _derive_slug("") == "reason"


def test_unique_slug_appends_suffix():
    taken = {"foo"}
    assert _unique_slug("foo", taken) == "foo_2"
    taken.add("foo_2")
    assert _unique_slug("foo", taken) == "foo_3"


def test_unique_slug_returns_base_when_free():
    assert _unique_slug("bar", set()) == "bar"


def test_unique_slug_respects_64_char_limit():
    base = "x" * 64
    taken = {base}
    out = _unique_slug(base, taken)
    assert len(out) <= 64
    assert out.endswith("_2")


def test_unique_slug_long_collision_chain():
    base = "y" * 64
    taken = {base} | {f"{base[:63]}_{i}" for i in range(2, 10)}
    out = _unique_slug(base, taken)
    assert len(out) <= 64
