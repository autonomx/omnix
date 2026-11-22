from __future__ import annotations

import json
from types import SimpleNamespace

import httpx

from app.platform.chat.assistant_context.models import AssistantContextBuildResult, AssistantContextChatRequest
from app.conversation.contracts import AssistantContextItem
from app.platform.chat.assistant_context.service import AssistantContextService
from app.providers.desktop_vision import (
    ClaudeCliDesktopVisionClient,
    CodexDesktopVisionClient,
    DesktopVisionClient,
    default_desktop_vision_client,
    is_remote_vision_endpoint,
)
from app.platform.research.web_search import should_search_automatically
import pytest

# Uses the PostgreSQL-backed runtime; runs in the test-postgres job.
pytestmark = pytest.mark.postgres


class FakeProvider:
    def __init__(self) -> None:
        self.calls = []

    def chat_completion(self, *, messages, model, stream=False):
        self.calls.append({"messages": messages, "model": model, "stream": stream})
        return SimpleNamespace(content="The desktop shows the Omnix chat window.", model=model or "vision-chat", usage={})


class FakeContextService:
    def build(self, request):
        assert request.content == "What is happening right now?"
        assert request.web_research_mode == "quick"
        assert request.internal_research_warnings == [
            "legacy_research_alias_deprecated:web_search_mode",
            "legacy_research_alias_deprecated:mode:automatic",
        ]
        assert request.desktop_image_data_url == "data:image/jpeg;base64,AAAA"
        return AssistantContextBuildResult(
            items=[
                AssistantContextItem(
                    source_id="web_search",
                    title="Current release note",
                    content="Omnix shipped a new live voice update today.",
                    url="https://example.test/release",
                ),
                AssistantContextItem(
                    source_id="desktop_vision",
                    title="Desktop observation",
                    content="A browser window is open to the Omnix assistant.",
                ),
            ],
            diagnostics={"web_search_status": "completed", "desktop_status": "completed"},
        )


class RecordingVisionClient:
    def __init__(self) -> None:
        self.calls = []

    def describe(self, image_data_url, question, model_id=None, **kwargs):
        self.calls.append(
            {
                "image": image_data_url,
                "question": question,
                "model_id": model_id,
                **kwargs,
            }
        )
        return AssistantContextItem(
            source_id="desktop_vision",
            title="Desktop observation",
            content="The game moved from a corridor into an arena.",
            metadata={
                "model": "vision-model",
                "fallback_mode": "multi_image",
                "image_count": 2,
                "fallback_errors": [],
            },
        )


def image_data(label: str) -> str:
    return f"data:image/jpeg;base64,{label}"


def test_automatic_search_detection_targets_fresh_or_explicit_queries():
    assert should_search_automatically("Search the web for current Qwen releases") is True
    assert should_search_automatically("What is the latest weather forecast?") is True
    assert should_search_automatically("Write a timeless fantasy greeting") is False


def test_temporal_vision_sends_history_before_high_detail_current_frame():
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.read()))
        return httpx.Response(200, json={"choices": [{"message": {"content": "The player entered a new room."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    observation = DesktopVisionClient(client=client, default_model="vision-model").describe(
        image_data("CURRENT"),
        "What changed?",
        history_image_data_url=image_data("HISTORY"),
        combined_image_data_url=image_data("COMBINED"),
        history_timestamps=[-5.0, -2.0, -0.75],
        capture_mode="temporal",
    )
    client.close()

    content = payloads[0]["messages"][1]["content"]
    images = [part["image_url"] for part in content if part["type"] == "image_url"]
    assert payloads[0]["max_tokens"] == 900
    assert images == [
        {"url": image_data("HISTORY"), "detail": "low"},
        {"url": image_data("CURRENT"), "detail": "high"},
    ]
    assert observation.metadata["fallback_mode"] == "multi_image"
    assert observation.metadata["image_count"] == 2


def test_temporal_vision_falls_back_to_combined_sheet_when_multiple_images_are_rejected():
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.read()))
        if len(payloads) == 1:
            return httpx.Response(400, json={"error": "multiple images unsupported"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Combined history resolved."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    observation = DesktopVisionClient(client=client, default_model="vision-model").describe(
        image_data("CURRENT"),
        "What changed?",
        history_image_data_url=image_data("HISTORY"),
        combined_image_data_url=image_data("COMBINED"),
        capture_mode="temporal",
    )
    client.close()

    second_content = payloads[1]["messages"][1]["content"]
    second_images = [part["image_url"] for part in second_content if part["type"] == "image_url"]
    assert second_images == [{"url": image_data("COMBINED"), "detail": "high"}]
    assert observation.metadata["fallback_mode"] == "combined_sheet"
    assert len(observation.metadata["fallback_errors"]) == 1


def test_vision_client_retries_one_image_without_optional_detail_hint():
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.read()))
        if len(payloads) == 1:
            return httpx.Response(400, json={"error": "invalid image"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "Image resolved."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    observation = DesktopVisionClient(client=client, default_model="vision-model").describe(
        image_data("CURRENT"),
        "What is visible?",
    )
    client.close()

    first_image = payloads[0]["messages"][1]["content"][1]["image_url"]
    second_image = payloads[1]["messages"][1]["content"][1]["image_url"]
    assert first_image == {"url": image_data("CURRENT"), "detail": "high"}
    assert second_image == {"url": image_data("CURRENT")}
    assert observation.content == "Image resolved."


def test_vision_client_auto_selects_available_vision_model_when_unconfigured():
    payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"id": "local-text-model"},
                        {"id": "qwen2.5-vl-7b-instruct"},
                    ]
                },
            )
        payload = json.loads(request.content.decode("utf-8"))
        payloads.append(payload)
        return httpx.Response(200, json={"choices": [{"message": {"content": "The desktop is visible."}}]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    observation = DesktopVisionClient(client=client).describe(
        image_data("CURRENT"),
        "Can you see the screen?",
    )
    client.close()

    assert payloads[0]["model"] == "qwen2.5-vl-7b-instruct"
    assert observation.content == "The desktop is visible."
    assert observation.metadata["model"] == "qwen2.5-vl-7b-instruct"


def test_codex_desktop_vision_uses_luna_app_server_image_input():
    calls = []

    class FakeCodexProvider:
        def chat_completion(self, messages, model, stream=False, **kwargs):
            calls.append({"messages": messages, "model": model, "stream": stream, "kwargs": kwargs})
            return SimpleNamespace(content="Luna can inspect the desktop.", model=model)

    observation = CodexDesktopVisionClient(
        default_model="llm:chatgpt_codex:gpt-5.6-luna",
        provider_factory=FakeCodexProvider,
    ).describe(image_data("CURRENT"), "What is visible?")

    assert calls[0]["model"] == "gpt-5.6-luna"
    assert calls[0]["stream"] is False
    user_message = calls[0]["messages"][1]
    assert user_message.vision_images == [{"data": image_data("CURRENT")}]
    assert observation.content == "Luna can inspect the desktop."
    assert observation.metadata["provider"] == "chatgpt_codex"
    assert observation.metadata["base_url"] == "codex://app-server"


def test_default_desktop_vision_routes_active_codex_profile_to_luna(monkeypatch):
    monkeypatch.setattr(
        "app.settings.access.load_settings",
        lambda: {
            "settings_control_center": {
                "global": {"providers": {"llm": "chatgpt_codex"}},
                "providerConfigs": {"chatgptCodex": {"model": "gpt-5.6-luna"}},
            }
        },
    )

    client = default_desktop_vision_client()

    assert isinstance(client, CodexDesktopVisionClient)
    assert client.default_model == "gpt-5.6-luna"


def test_default_desktop_vision_recognizes_plain_luna_model_id(monkeypatch):
    monkeypatch.setattr(
        "app.settings.access.load_settings",
        lambda: {
            "settings_control_center": {
                "global": {"providers": {"llm": "lmstudio"}},
                "assistant": {"desktopCompanionVisionModelId": "gpt-5.6-luna"},
            }
        },
    )

    client = default_desktop_vision_client()

    assert isinstance(client, CodexDesktopVisionClient)
    assert client.default_model == "gpt-5.6-luna"


def test_default_desktop_vision_respects_explicit_local_model_override(monkeypatch):
    monkeypatch.setattr(
        "app.settings.access.load_settings",
        lambda: {
            "settings_control_center": {
                "global": {"providers": {"llm": "chatgpt_codex"}},
                "assistant": {"desktopCompanionVisionModelId": "qwen2.5-vl"},
            }
        },
    )

    client = default_desktop_vision_client()

    assert isinstance(client, DesktopVisionClient)
    assert not isinstance(client, CodexDesktopVisionClient)


def _profile(monkeypatch, **profile):
    for name in ("OMNIX_VISION_BASE_URL", "OMNIX_VISION_MODEL", "OMNIX_VISION_PROVIDER"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("app.settings.access.load_settings", lambda: {"settings_control_center": profile})


def test_with_no_vision_model_a_claude_chat_looks_with_its_own_claude_model(monkeypatch):
    _profile(
        monkeypatch,
        **{"global": {"providers": {"llm": "claude_cli"}, "models": {"chat": "llm:claude_cli:claude-haiku-4-5-20251001"}},
           "providerConfigs": {"claudeCli": {"model": "sonnet"}}},
    )

    client = default_desktop_vision_client()

    assert isinstance(client, ClaudeCliDesktopVisionClient)
    assert client.default_model == "claude-haiku-4-5-20251001"
    # Anthropic is off this machine: the remote-consent check applies.
    assert is_remote_vision_endpoint(client.base_url)


def test_a_claude_chat_with_another_chat_model_route_uses_the_clis_model(monkeypatch):
    _profile(monkeypatch, **{"global": {"providers": {"llm": "claude_cli"}},
                             "providerConfigs": {"claudeCli": {"model": "haiku"}}})

    assert default_desktop_vision_client().default_model == "haiku"


def test_a_claude_vision_reference_picks_the_claude_cli_whatever_the_chat(monkeypatch):
    _profile(monkeypatch, **{"global": {"providers": {"llm": "lmstudio"}},
                             "assistant": {"desktopCompanionVisionModelId": "claude_cli:sonnet"}})

    client = default_desktop_vision_client()

    assert isinstance(client, ClaudeCliDesktopVisionClient)
    assert client.default_model == "sonnet"


def test_with_no_vision_model_a_local_chat_looks_with_its_own_model(monkeypatch):
    _profile(
        monkeypatch,
        **{"global": {"providers": {"llm": "lmstudio"}, "models": {"chat": "llm:lmstudio:qwen3.8-27b"}},
           "providerConfigs": {"lmstudio": {"baseUrl": "http://localhost:1234", "model": "other"}}},
    )

    client = default_desktop_vision_client()

    assert type(client) is DesktopVisionClient
    assert (client.base_url, client.default_model, client.follows_chat) == (
        "http://localhost:1234/v1", "qwen3.8-27b", True,
    )


def test_an_explicit_local_vision_model_does_not_follow_the_chat(monkeypatch):
    _profile(monkeypatch, **{"global": {"providers": {"llm": "claude_cli"}},
                             "assistant": {"desktopCompanionVisionModelId": "gemma-4-12b"}})

    client = default_desktop_vision_client()

    assert type(client) is DesktopVisionClient and client.follows_chat is False


def test_claude_cli_vision_sends_the_picture_through_the_cli_provider():
    calls = []

    class FakeClaudeProvider:
        def chat_completion(self, messages, model, stream=False, **kwargs):
            calls.append({"messages": messages, "model": model, "stream": stream, **kwargs})
            return SimpleNamespace(content="A person at a desk.", model=model)

    observation = ClaudeCliDesktopVisionClient(
        default_model="claude_cli:haiku", provider_factory=FakeClaudeProvider,
    ).describe(image_data("CURRENT"), "Can you see me?")

    assert calls[0]["model"] == "haiku" and calls[0]["stream"] is False
    # Haiku thinks at any effort: about 2.2 s to the first word instead of 0.55 s, longer than a spoken turn waits.
    assert calls[0]["thinking"] is False
    assert calls[0]["messages"][1].vision_images == [{"data": image_data("CURRENT")}]
    assert observation.content == "A person at a desk."
    assert (observation.metadata["provider"], observation.metadata["base_url"]) == ("claude_cli", "claude-cli://local")


def test_the_call_camera_offers_show_for_a_chat_model_that_looks():
    from app.platform.chat.live_call_camera import camera_vision

    claude = ClaudeCliDesktopVisionClient(provider_factory=lambda: None)
    refused = camera_vision(client_factory=lambda: claude, assistant_settings=lambda: {})
    assert (refused.available, refused.reason) == (False, "remote_vision_not_allowed")
    allowed = camera_vision(client_factory=lambda: claude,
                            assistant_settings=lambda: {"desktopCompanionRemoteVisionAllowed": True})
    assert (allowed.available, allowed.reason) == (True, "ready")

    local = DesktopVisionClient(base_url="http://localhost:1234/v1")
    local.follows_chat = True
    assert camera_vision(client_factory=lambda: local, assistant_settings=lambda: {}).available


def test_context_service_passes_temporal_images_and_records_resolution_mode():
    vision = RecordingVisionClient()
    service = AssistantContextService(desktop_vision_factory=lambda: vision)
    result = service.build(
        AssistantContextChatRequest(
            content="What just happened?",
            model_id="llm:lmstudio:text-model",
            vision_model_id="vision-model",
            desktop_current_image_data_url=image_data("CURRENT"),
            desktop_history_image_data_url=image_data("HISTORY"),
            desktop_combined_image_data_url=image_data("COMBINED"),
            desktop_history_timestamps=[-5.0, -2.0],
            desktop_capture_mode="temporal",
        )
    )

    assert vision.calls[0]["history_image_data_url"] == image_data("HISTORY")
    assert vision.calls[0]["combined_image_data_url"] == image_data("COMBINED")
    assert vision.calls[0]["capture_mode"] == "temporal"
    assert result.diagnostics["desktop_status"] == "completed"
    assert result.diagnostics["desktop_fallback_mode"] == "multi_image"
    assert result.diagnostics["desktop_image_count"] == 2


def test_context_service_keeps_desktop_failure_visible_to_chat_prompt():
    class FailingVisionClient:
        def describe(self, *args, **kwargs):
            raise RuntimeError("no vision model configured")

    service = AssistantContextService(desktop_vision_factory=FailingVisionClient)
    result = service.build(
        AssistantContextChatRequest(
            content="Can you see the screen?",
            desktop_current_image_data_url=image_data("CURRENT"),
        )
    )

    assert result.diagnostics["desktop_status"] == "failed"
    assert result.items[0].source_id == "desktop_vision"
    assert "desktop sharing is active" in result.items[0].content.lower()
    assert "no vision model configured" in result.items[0].content




def test_a_vision_endpoint_outside_the_url_policy_is_refused_before_any_request(monkeypatch):
    """The configured endpoint passes the outbound URL policy; redirects are not followed (WP-4.10)."""
    from app.security.url_policy import UrlPolicyError

    def no_client(*args, **kwargs):
        raise AssertionError("no connection may be opened")

    monkeypatch.setattr(httpx, "Client", no_client)
    with pytest.raises(UrlPolicyError, match="link_local_address_blocked"):
        DesktopVisionClient(base_url="http://169.254.169.254/v1", default_model="m").describe(image_data("CURRENT"), "What is shown?")
