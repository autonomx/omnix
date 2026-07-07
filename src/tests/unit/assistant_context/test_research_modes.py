import pytest
from pydantic import ValidationError

from app.assistant_context.models import AssistantContextChatRequest
from app.research import normalize_research_mode, resolve_research_mode
from app.research.compatibility import (
    research_compatibility_status,
    reset_research_compatibility_telemetry,
)


def test_canonical_mode_normalization_rejects_retired_values() -> None:
    assert normalize_research_mode("automatic") == "disabled"
    assert normalize_research_mode("manual") == "disabled"
    assert normalize_research_mode("quick_search") == "disabled"
    assert normalize_research_mode("deep_research") == "disabled"
    assert normalize_research_mode("quick") == "quick"
    assert normalize_research_mode("deep") == "deep"


def test_mode_precedence_uses_turn_then_conversation_then_profile() -> None:
    turn = resolve_research_mode(
        turn_override="deep",
        conversation_override="quick",
        profile_default="disabled",
        deep_enabled=True,
    )
    conversation = resolve_research_mode(
        conversation_override="quick",
        profile_default="deep",
        deep_enabled=True,
    )
    profile = resolve_research_mode(profile_default="quick")
    assert (turn.effective_mode, turn.source) == ("deep", "turn")
    assert (conversation.effective_mode, conversation.source) == ("quick", "conversation")
    assert (profile.effective_mode, profile.source) == ("quick", "profile")


def test_runtime_availability_never_enables_search_silently() -> None:
    quick = resolve_research_mode(turn_override="quick", quick_enabled=False)
    deep = resolve_research_mode(turn_override="deep", deep_enabled=False)
    assert quick.effective_mode == "disabled"
    assert deep.effective_mode == "disabled"
    assert quick.warning
    assert deep.warning


def test_temporary_server_aliases_are_normalized_warned_and_counted(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_RESEARCH_LEGACY_ALIASES_ENABLED", "1")
    monkeypatch.setenv("OMNIX_RESEARCH_LEGACY_ALIAS_SUNSET", "2026-09-01")
    reset_research_compatibility_telemetry()

    request = AssistantContextChatRequest(
        content="Find it",
        web_search_mode="automatic",
        web_search_requested=True,
    )
    status = research_compatibility_status()

    assert request.web_research_mode == "quick"
    assert request.internal_research_warnings == [
        "legacy_research_alias_deprecated:web_search_mode",
        "legacy_research_alias_deprecated:web_search_requested",
        "legacy_research_alias_deprecated:mode:automatic",
    ]
    assert "web_search_mode" not in request.model_dump()
    assert "web_search_requested" not in request.model_dump()
    assert status.aliases_enabled is True
    assert status.sunset == "2026-09-01"
    assert status.total_legacy_requests == 1
    assert status.alias_counts["web_search_mode"] == 1
    assert status.alias_counts["web_search_requested"] == 1
    assert status.alias_counts["mode:automatic"] == 1


def test_server_aliases_can_be_disabled_without_affecting_canonical_requests(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_RESEARCH_LEGACY_ALIASES_ENABLED", "0")
    with pytest.raises(ValidationError, match="legacy_research_aliases_disabled"):
        AssistantContextChatRequest(content="Find it", web_search_mode="manual")

    canonical = AssistantContextChatRequest(content="Research it", web_research_mode="deep")
    assert canonical.web_research_mode == "deep"
