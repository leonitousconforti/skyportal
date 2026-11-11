"""Check a URL a user asks the server to send requests (and their key) to."""

__all__ = ["check_user_base_url"]

import ipaddress
import socket
from urllib.parse import urlsplit

# IPv6 ranges that reach the IPv4 address in their last 32 bits (IPv4-mapped,
# SIIT, NAT64), so that IPv4 address is the one judged.
_IPV4_IN_IPV6 = [
    ipaddress.ip_network(net)
    for net in ("::ffff:0:0/96", "::ffff:0:0:0/96", "64:ff9b::/96")
]


def check_user_base_url(url: str) -> str:
    """The stripped `url`, or ValueError unless it is https to a public host."""
    url = url.strip() if isinstance(url, str) else ""
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname:
        raise ValueError("The base URL must start with https:// and name a host")
    if "@" in parts.netloc:
        raise ValueError("The base URL must not contain a username or password")
    # getaddrinfo (IDNA 2003) and httpx (IDNA 2008) encode a non-ASCII host
    # differently, so the check would resolve another name than the request.
    if not parts.hostname.isascii():
        raise ValueError("The base URL host must be ASCII (use its xn-- form)")

    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, None)}
    except (OSError, UnicodeError):
        raise ValueError(
            f"The base URL host {parts.hostname} does not resolve"
        ) from None
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if any(ip in net for net in _IPV4_IN_IPV6):
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
        if not ip.is_global:
            raise ValueError(
                f"The base URL host {parts.hostname} is not a public address"
            )
    return url
