from __future__ import annotations

from app.assistant_context.models import AssistantContextItem
from app.desktop_companion.preflight import (
    DesktopCompanionPreflightRequest,
    DesktopCompanionPreflightService,
    is_remote_vision_endpoint,
)


class FakeClient:
    base_url = "http://127.0.0.1:1234/v1"
    default_model = "fake-vl"

    def describe(self, *args, **kwargs) -> AssistantContextItem:
        return AssistantContextItem(
            source_id="desktop_vision",
            title="Desktop observation",
            content="A blank test image is visible.",
            metadata={"model": "fake-vl"},
        )


class RemoteClient(FakeClient):
    base_url = "https://vision.example.test/v1"


def test_local_preflight_verifies_image_capability() -> None:
    clock = iter([1.0, 1.125])
    service = DesktopCompanionPreflightService(
        client_factory=FakeClient,
        clock=lambda: next(clock),
    )

    result = service.check(DesktopCompanionPreflightRequest())

    assert result.ready is True
    assert result.model_id == "fake-vl"
    assert result.endpoint == "http://127.0.0.1:1234/v1"
    assert result.remote is False
    assert result.latency_ms == 125.0


def test_remote_provider_requires_explicit_consent_before_image_call() -> None:
    class ExplodingRemote(RemoteClient):
        def describe(self, *args, **kwargs):
            raise AssertionError("remote provider must not receive an image")

    service = DesktopCompanionPreflightService(client_factory=ExplodingRemote)
    result = service.check(DesktopCompanionPreflightRequest(remote_vision_allowed=False))

    assert result.ready is False
    assert result.remote is True
    assert result.reason == "remote_vision_not_allowed"


def test_endpoint_classification_handles_loopback_and_remote_hosts() -> None:
    assert is_remote_vision_endpoint("http://localhost:1234/v1") is False
    assert is_remote_vision_endpoint("http://127.0.0.2:1234/v1") is False
    assert is_remote_vision_endpoint("https://vision.example.com/v1") is True
