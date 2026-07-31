from app.pipeline.url_hash import normalize_url, url_hash


def _same(a: str, b: str) -> bool:
    return url_hash(a) == url_hash(b)


# --- the reported case: same job, differing noise params -------------------

def test_tracking_and_locale_params_ignored():
    assert _same(
        "https://mway.jobs.personio.de/job/2053046?language=de&src=LinkedIn",
        "https://mway.jobs.personio.de/job/2053046?language=de",
    )
    assert _same(
        "https://mway.jobs.personio.de/job/2053046?language=de&src=LinkedIn",
        "https://mway.jobs.personio.de/job/2053046",
    )


def test_utm_params_ignored():
    assert _same(
        "https://x.test/job/1?utm_source=nl&utm_campaign=jul&utm_medium=email",
        "https://x.test/job/1",
    )


# --- meaningful params are preserved --------------------------------------

def test_meaningful_query_param_distinguishes():
    assert not _same("https://x.test/jobs?gh_jid=123", "https://x.test/jobs?gh_jid=456")


def test_param_order_does_not_matter():
    assert _same("https://x.test/j?a=1&b=2", "https://x.test/j?b=2&a=1")


# --- structural normalization ---------------------------------------------

def test_trailing_slash_ignored():
    assert _same("https://x.test/job/1", "https://x.test/job/1/")


def test_fragment_ignored():
    assert _same("https://x.test/job/1#apply", "https://x.test/job/1")


def test_scheme_and_host_case_insensitive():
    assert _same("https://X.TEST/job/1", "https://x.test/job/1")


def test_default_port_ignored():
    assert _same("https://x.test:443/job/1", "https://x.test/job/1")
    assert _same("http://x.test:80/job/1", "http://x.test/job/1")


def test_whitespace_stripped():
    assert _same("  https://x.test/job/1  ", "https://x.test/job/1")


# --- things that must stay distinct ---------------------------------------

def test_different_paths_distinct():
    assert not _same("https://x.test/job/1", "https://x.test/job/2")


def test_different_hosts_distinct():
    assert not _same("https://a.test/job/1", "https://b.test/job/1")


def test_scheme_distinct():
    # http vs https are different endpoints; keep them apart
    assert not _same("http://x.test/job/1", "https://x.test/job/1")


# --- normalize_url output is stable & idempotent --------------------------

def test_normalize_is_idempotent():
    once = normalize_url("https://X.test/job/1/?src=LinkedIn&b=2&a=1#x")
    twice = normalize_url(once)
    assert once == twice


def test_hash_is_64_hex():
    h = url_hash("https://x.test/job/1")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)
