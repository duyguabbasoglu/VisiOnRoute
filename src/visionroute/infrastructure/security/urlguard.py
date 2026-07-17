"""SSRF-safe URL validation for any user-supplied URL (webhooks, feeds, RTSP).

Rejects non-allowlisted schemes, credentials-in-URL, and hosts that resolve to
private, loopback, link-local, or reserved address space. Resolution happens
here so a hostname cannot smuggle a private target past the check.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse


class UnsafeUrlError(ValueError):
    """Raised when a URL is not safe to fetch/connect to."""


@dataclass(frozen=True)
class UrlPolicy:
    allowed_schemes: frozenset[str] = frozenset({"https"})
    allow_http: bool = False


_DEFAULT_POLICY = UrlPolicy()


def _is_public_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


def validate_url(
    url: str,
    *,
    policy: UrlPolicy | None = None,
    resolver: object | None = None,
) -> str:
    """Return the URL if safe; otherwise raise ``UnsafeUrlError``.

    ``resolver`` (a callable host->list[str]) is injectable for tests.
    """
    policy = policy or _DEFAULT_POLICY
    parsed = urlparse(url)

    allowed = set(policy.allowed_schemes)
    if policy.allow_http:
        allowed.add("http")
    if parsed.scheme not in allowed:
        msg = f"İzin verilmeyen şema: {parsed.scheme or '(yok)'}"
        raise UnsafeUrlError(msg)
    if parsed.username or parsed.password:
        msg = "URL içinde kimlik bilgisi taşınamaz."
        raise UnsafeUrlError(msg)
    if not parsed.hostname:
        msg = "URL geçerli bir sunucu adı içermiyor."
        raise UnsafeUrlError(msg)

    resolve = resolver if callable(resolver) else _default_resolver
    try:
        addresses = resolve(parsed.hostname)
    except OSError as exc:
        msg = f"Sunucu adı çözümlenemedi: {parsed.hostname}"
        raise UnsafeUrlError(msg) from exc

    if not addresses:
        msg = f"Sunucu adı için adres bulunamadı: {parsed.hostname}"
        raise UnsafeUrlError(msg)
    for ip in addresses:
        if not _is_public_ip(ip):
            msg = "URL özel/dahili bir ağ adresine çözümleniyor; engellendi."
            raise UnsafeUrlError(msg)
    return url


def _default_resolver(host: str) -> list[str]:
    infos = socket.getaddrinfo(host, None)
    return [str(info[4][0]) for info in infos]
