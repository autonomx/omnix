import httpx
import pytest

from app.research.outbound_web import OutboundWebPolicy, OutboundWebPolicyError


def public_resolver(hostname: str, port: int):
    if hostname == "private.test":
        return ["127.0.0.1"]
    return ["93.184.216.34"]


def test_policy_blocks_private_literal_mapped_ipv6_userinfo_and_ports() -> None:
    policy = OutboundWebPolicy(resolver=public_resolver)
    blocked = (
        "http://127.0.0.1/private",
        "http://[::1]/private",
        "http://[::ffff:127.0.0.1]/private",
        "https://user:pass@example.test/private",
        "https://example.test:8443/private",
    )
    for url in blocked:
        with pytest.raises(OutboundWebPolicyError):
            policy.validate_url(url)


def test_policy_revalidates_every_redirect_target() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"location": "http://private.test/internal"})

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    policy = OutboundWebPolicy(resolver=public_resolver, client=client)
    with pytest.raises(OutboundWebPolicyError, match="non_public_address_blocked"):
        policy.fetch("https://example.test/start")
    client.close()


def test_policy_enforces_content_type_and_expansion_limits() -> None:
    responses = iter(
        (
            httpx.Response(200, headers={"content-type": "image/png"}, content=b"png"),
            httpx.Response(200, headers={"content-type": "text/html"}, content=b"x" * 64),
        )
    )
    client = httpx.Client(
        transport=httpx.MockTransport(lambda request: next(responses)),
        follow_redirects=False,
    )
    policy = OutboundWebPolicy(
        resolver=public_resolver,
        client=client,
        max_compressed_bytes=32,
        max_decompressed_bytes=48,
    )
    with pytest.raises(OutboundWebPolicyError, match="unsupported_response_content_type"):
        policy.fetch("https://example.test/image")
    with pytest.raises(OutboundWebPolicyError, match="decompressed_response_too_large"):
        policy.fetch("https://example.test/large")
    client.close()


def test_policy_returns_bounded_text_response() -> None:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "text/plain; charset=utf-8"},
                content=b"bounded response",
            )
        ),
        follow_redirects=False,
    )
    result = OutboundWebPolicy(resolver=public_resolver, client=client).fetch(
        "https://example.test/article"
    )
    assert result.content == b"bounded response"
    assert result.content_type == "text/plain"
    assert result.redirect_count == 0
    client.close()
