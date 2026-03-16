"""SSRF-safe URL validation for user-supplied URLs.

@decision DEC-SEC-003
@title SSRF protection via IP range blocking before HTTP fetch
@status accepted
@rationale User-supplied URLs (evidence sources, research) are fetched by the
backend. Without SSRF protection, an attacker could supply URLs like
http://169.254.169.254/latest/meta-data/ (AWS instance metadata) or
http://192.168.1.1/ (internal router) to exfiltrate data from the server's
network. Protection is applied at the URL parsing stage before any HTTP
connection is made: the hostname is resolved to IP(s), and any IP in a private,
loopback, link-local, or reserved range is rejected. For IP literal URLs (e.g.
http://10.0.0.1/) the IP is checked directly without DNS resolution to prevent
DNS rebinding attacks. Only http and https schemes are allowed — file://, ftp://,
gopher:// etc are rejected outright.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


# Blocked IP networks (private, loopback, link-local, reserved).
# RFC 1918: 10/8, 172.16/12, 192.168/16
# RFC 3927: 169.254/16 (link-local / AWS metadata endpoint)
# RFC 3513: ::1/128 (IPv6 loopback), fc00::/7 (IPv6 ULA)
# Special: 0.0.0.0/8, 127.0.0.0/8, 240.0.0.0/4 (reserved/multicast)
_BLOCKED_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]

_ALLOWED_SCHEMES = {"http", "https"}


def _is_private_ip(addr: str) -> bool:
    """Return True if *addr* is in a private/reserved range."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        # Not a valid IP address string — treat as non-private
        return False
    return any(ip in net for net in _BLOCKED_NETWORKS)


def validate_url_not_ssrf(url: str) -> None:
    """Validate that *url* is safe to fetch (no SSRF risk).

    Checks:
    1. Scheme must be http or https.
    2. Hostname must not be 'localhost' or resolve to a private/reserved IP.
    3. For IP literal URLs, the IP is checked directly.

    Raises:
        ValueError: with a descriptive message if the URL fails validation.

    This function is synchronous and performs a blocking DNS lookup. It is
    intended to be called before handing a URL to an async HTTP client.
    For high-throughput paths, consider caching resolved IPs per hostname.
    """
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Malformed URL: {url!r}") from exc

    scheme = (parsed.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Forbidden URL scheme {scheme!r}. Only http and https are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError(f"URL has no hostname: {url!r}")

    # Reject 'localhost' and numeric loopback without DNS lookup
    if hostname.lower() == "localhost":
        raise ValueError(
            "Forbidden hostname 'localhost' — SSRF protection blocks local addresses."
        )

    # Try to parse hostname as an IP literal first (fast path, no DNS)
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if _is_private_ip(str(ip_obj)):
            raise ValueError(
                f"Forbidden IP address {hostname!r} — SSRF protection blocks "
                "private/reserved/loopback ranges."
            )
        # Public IP literal — allowed
        return
    except ValueError as ip_exc:
        # If our SSRF block raised, re-raise it
        if "Forbidden" in str(ip_exc) or "SSRF" in str(ip_exc):
            raise
        # Otherwise hostname is not an IP literal — proceed to DNS resolution

    # Resolve hostname to IPs and check each
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror as exc:
        raise ValueError(
            f"Cannot resolve hostname {hostname!r}: {exc}"
        ) from exc

    for _family, _type, _proto, _canonname, sockaddr in results:
        resolved_ip = sockaddr[0]
        if _is_private_ip(resolved_ip):
            raise ValueError(
                f"Hostname {hostname!r} resolves to private/reserved IP "
                f"{resolved_ip!r} — SSRF protection blocks this address."
            )
