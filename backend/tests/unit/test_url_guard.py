"""Tests for SSRF protection via validate_public_url."""
import socket

import pytest

from app.crawler.url_guard import UnsafeURLError, validate_public_url


def _make_getaddrinfo(ip: str):
    """Return a monkeypatched getaddrinfo that resolves any host to the given IP."""
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port or 80))]
    return fake_getaddrinfo


# ── Rejected URLs ────────────────────────────────────────────────────────────

def test_rejects_localhost(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("127.0.0.1"))
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("http://localhost")


def test_rejects_127(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("127.0.0.1"))
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("http://127.0.0.1")


def test_rejects_private_10(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("10.0.0.1"))
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("http://10.0.0.1")


def test_rejects_link_local(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("169.254.169.254"))
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("http://169.254.169.254")


def test_rejects_ipv6_loopback(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::1", port or 80, 0, 0))]
    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("http://[::1]")


def test_rejects_file_scheme():
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("file:///etc/passwd")


def test_rejects_ftp_scheme():
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("ftp://x")


def test_rejects_unspecified(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("0.0.0.0"))
    with pytest.raises((UnsafeURLError, ValueError)):
        validate_public_url("http://0.0.0.0")


# ── Accepted URLs ────────────────────────────────────────────────────────────

def test_accepts_example_com(monkeypatch):
    # Mock resolver so tests are deterministic and don't hit real DNS
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("93.184.216.34"))
    validate_public_url("https://example.com")  # should not raise


def test_accepts_public_ip(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _make_getaddrinfo("93.184.216.34"))
    validate_public_url("http://93.184.216.34")  # should not raise
