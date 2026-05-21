from app.util.slug import slugify


def test_basic():
    assert slugify("Acme Corp") == "acme-corp"


def test_umlauts():
    assert slugify("Müller GmbH") == "muller-gmbh"


def test_punctuation():
    assert slugify("C++ / Rust Engineer (Senior)!") == "c-rust-engineer-senior"


def test_empty():
    assert slugify("") == ""
    assert slugify(None) == ""


def test_truncate():
    s = slugify("a" * 100, max_len=10)
    assert s == "a" * 10


def test_truncate_trims_trailing_hyphen():
    s = slugify("abcdefghij-klmnop", max_len=11)
    assert s == "abcdefghij"
