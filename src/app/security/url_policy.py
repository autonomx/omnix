"""Outbound URL policy for configurable endpoints (WP-4.10).

Provider base URLs and similar settings name servers Omnix will call. The
policy keeps them from reaching what a request should never reach:

- schemes: http and https only, with a host and no credentials;
- always blocked: link-local addresses (169.254.0.0/16, fe80::/10, which hold
  cloud metadata services), metadata hostnames, unspecified, multicast and
  reserved addresses;
- loopback is allowed (local model servers);
- private networks: the CIDRs in ``OMNIX_ALLOWED_PRIVATE_NETWORKS``
  (comma-separated). Unset, they are allowed while sign-in is off (one local
  user configuring their own LAN servers) and refused when sign-in is on;
- public addresses are allowed.

``check_outbound_url`` runs when a setting is saved and, with
``resolve=True``, before each connection so a hostname that later resolves to
a blocked address is refused.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from urllib.parse import urlsplit

from app.config.env import env_str

METADATA_HOSTNAMES = frozenset({
    "metadata",
    "metadata.google.internal",
    "metadata.goog",
    "metadata.azure.com",
    "instance-data",
    "instance-data.ec2.internal",
})

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], Iterable[str]]


class UrlPolicyError(ValueError):
    """The URL may not be used as an outbound endpoint."""


def _resolve(hostname: str, port: int) -> list[str]:
    try:
        rows = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise UrlPolicyError("hostname_resolution_failed") from exc
    return sorted({str(row[4][0]) for row in rows})


def allowed_private_networks() -> list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None:
    """Configured private networks; ``None`` means every private network."""
    configured = (env_str("OMNIX_ALLOWED_PRIVATE_NETWORKS", "") or "").strip()
    if configured:
        try:
            return [ipaddress.ip_network(item.strip(), strict=False) for item in configured.split(",") if item.strip()]
        except ValueError as exc:
            raise UrlPolicyError("OMNIX_ALLOWED_PRIVATE_NETWORKS must be comma-separated CIDRs") from exc
    from app.security.auth.settings import resolve_auth_settings

    return [] if resolve_auth_settings().enforced else None


def check_address(address: IPAddress) -> None:
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        address = address.ipv4_mapped
    if address.is_loopback:
        return
    if address.is_link_local:
        raise UrlPolicyError("link_local_address_blocked")
    if address.is_unspecified or address.is_multicast or address.is_reserved:
        raise UrlPolicyError("reserved_address_blocked")
    if address.is_private:
        networks = allowed_private_networks()
        if networks is None or any(address in network for network in networks):
            return
        raise UrlPolicyError("private_address_not_allowed")


def check_outbound_url(url: str, *, resolve: bool = False, resolver: Resolver = _resolve) -> str:
    """Validate ``url``; with ``resolve``, also every address its host resolves to."""
    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        raise UrlPolicyError("url_scheme_not_allowed")
    if parsed.username or parsed.password:
        raise UrlPolicyError("url_credentials_not_allowed")
    hostname = (parsed.hostname or "").rstrip(".").lower()
    if not hostname:
        raise UrlPolicyError("url_host_required")
    if hostname in METADATA_HOSTNAMES:
        raise UrlPolicyError("metadata_host_blocked")
    try:
        literal: IPAddress | None = ipaddress.ip_address(hostname)
    except ValueError:
        literal = None
    if literal is not None:
        check_address(literal)
    elif resolve:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            addresses = list(resolver(hostname, port))
        except UrlPolicyError:
            # A name that does not resolve reaches nothing; the connection
            # itself reports the failure.
            return url
        for value in addresses:
            check_address(ipaddress.ip_address(value))
    return url


__all__ = ["METADATA_HOSTNAMES", "UrlPolicyError", "allowed_private_networks", "check_address", "check_outbound_url"]
