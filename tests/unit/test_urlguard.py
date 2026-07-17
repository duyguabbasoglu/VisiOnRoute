"""SSRF URL guard unit tests."""

import pytest

from visionroute.infrastructure.security.urlguard import (
    UnsafeUrlError,
    UrlPolicy,
    validate_url,
)


def _resolver(mapping: dict[str, list[str]]):
    def resolve(host: str) -> list[str]:
        return mapping.get(host, [])

    return resolve


def test_public_https_allowed() -> None:
    url = "https://api.example.com/webhook"
    assert validate_url(url, resolver=_resolver({"api.example.com": ["93.184.216.34"]})) == url


def test_private_ip_blocked() -> None:
    with pytest.raises(UnsafeUrlError, match="özel/dahili"):
        validate_url(
            "https://internal.example.com",
            resolver=_resolver({"internal.example.com": ["10.0.0.5"]}),
        )


def test_loopback_blocked() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url("https://x.example.com", resolver=_resolver({"x.example.com": ["127.0.0.1"]}))


def test_link_local_metadata_endpoint_blocked() -> None:
    # AWS metadata service — classic SSRF target.
    with pytest.raises(UnsafeUrlError):
        validate_url(
            "https://metadata.example.com",
            resolver=_resolver({"metadata.example.com": ["169.254.169.254"]}),
        )


def test_http_scheme_blocked_by_default() -> None:
    with pytest.raises(UnsafeUrlError, match="şema"):
        validate_url("http://api.example.com", resolver=_resolver({"api.example.com": ["1.2.3.4"]}))


def test_credentials_in_url_blocked() -> None:
    with pytest.raises(UnsafeUrlError, match="kimlik"):
        validate_url(
            "https://user:pass@api.example.com",
            resolver=_resolver({"api.example.com": ["1.2.3.4"]}),
        )


def test_unresolvable_host_blocked() -> None:
    with pytest.raises(UnsafeUrlError):
        validate_url("https://nope.example.com", resolver=_resolver({}))


def test_http_allowed_when_policy_permits() -> None:
    url = "http://api.example.com"
    policy = UrlPolicy(allow_http=True)
    assert validate_url(url, policy=policy, resolver=_resolver({"api.example.com": ["1.2.3.4"]}))
