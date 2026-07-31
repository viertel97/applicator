import hashlib
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Query params that carry no identity — tracking, referral and locale noise.
# Two links that differ only in these point at the same job, so we drop them
# before hashing. Anything not listed here (e.g. a `gh_jid=` job id) is kept.
_TRACKING_PARAMS = frozenset(
    {
        "src",
        "source",
        "ref",
        "referrer",
        "referer",
        "refid",
        "trk",
        "trackingid",
        "originalsubdomain",
        "language",
        "lang",
        "locale",
        "hl",
        "gclid",
        "fbclid",
        "msclkid",
        "dclid",
        "yclid",
        "mc_cid",
        "mc_eid",
        "igshid",
        "gh_src",
        "_ga",
        "_gl",
    }
)

_DEFAULT_PORTS = {"http": 80, "https": 443}


def _is_tracking(key: str) -> bool:
    k = key.lower()
    return k in _TRACKING_PARAMS or k.startswith("utm_")


def normalize_url(url: str) -> str:
    """Canonicalize a URL so cosmetic differences collapse to one form.

    Lowercases scheme/host, drops the default port, the fragment and a trailing
    slash, removes tracking/locale query params, and sorts the rest. The result
    is deterministic and idempotent — feeding it back in returns itself.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()

    host = (parts.hostname or "").lower()
    port = parts.port
    if port is not None and _DEFAULT_PORTS.get(scheme) != port:
        netloc = f"{host}:{port}"
    else:
        netloc = host

    path = parts.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    kept = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not _is_tracking(k)
    ]
    kept.sort()
    query = urlencode(kept)

    return urlunsplit((scheme, netloc, path, query, ""))


def url_hash(url: str) -> str:
    return hashlib.sha256(normalize_url(url).lower().encode()).hexdigest()
