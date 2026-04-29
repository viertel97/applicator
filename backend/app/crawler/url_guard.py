"""SSRF protection: validate that a URL is safe to fetch."""
import ipaddress
import socket
from urllib.parse import urlparse


class UnsafeURLError(ValueError):
    """Raised when a URL resolves to a non-public address or has a disallowed scheme."""


def validate_public_url(url: str) -> None:
    """Validate that *url* is safe to fetch (public internet only).

    Raises UnsafeURLError if:
    - The scheme is not http or https.
    - The hostname resolves to a loopback, link-local, private, multicast,
      reserved, or unspecified address.
    """
    parsed = urlparse(url)

    # 1. Scheme check
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError(
            f"Disallowed URL scheme {parsed.scheme!r}. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise UnsafeURLError("URL has no hostname.")

    # 2. Resolve hostname and check every returned address
    try:
        infos = socket.getaddrinfo(hostname, parsed.port or 80)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve hostname {hostname!r}: {exc}") from exc

    if not infos:
        raise UnsafeURLError(f"Hostname {hostname!r} resolved to no addresses.")

    for family, _type, _proto, _canonname, sockaddr in infos:
        raw_ip = sockaddr[0]
        try:
            addr = ipaddress.ip_address(raw_ip)
        except ValueError:
            raise UnsafeURLError(f"Could not parse resolved IP address {raw_ip!r}.")

        _check_ip(addr, hostname)


def _check_ip(addr: ipaddress.IPv4Address | ipaddress.IPv6Address, hostname: str) -> None:
    """Raise UnsafeURLError if *addr* is a non-public address."""
    reasons = []
    if addr.is_loopback:
        reasons.append("loopback")
    if addr.is_link_local:
        reasons.append("link-local")
    if addr.is_private:
        reasons.append("private")
    if addr.is_multicast:
        reasons.append("multicast")
    if addr.is_reserved:
        reasons.append("reserved")
    if addr.is_unspecified:
        reasons.append("unspecified (0.0.0.0 / ::)")

    if reasons:
        raise UnsafeURLError(
            f"URL {hostname!r} resolves to {addr} which is a {', '.join(reasons)} address. "
            "Fetching internal/private addresses is not allowed."
        )
