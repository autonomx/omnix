from app.assistant_context.models import AssistantContextChatRequest
from app.research import normalize_research_mode, resolve_research_mode


def test_legacy_mode_values_normalize() -> None:
    assert normalize_research_mode("automatic") == "quick"
    assert normalize_research_mode("manual") == "quick"
    assert normalize_research_mode("deep_research") == "deep"
    assert normalize_research_mode("other") == "disabled"


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


def test_request_accepts_old_and_new_field_names() -> None:
    legacy = AssistantContextChatRequest(content="Find it", web_search_mode="automatic")
    current = AssistantContextChatRequest(content="Research it", web_research_mode="deep")
    assert legacy.web_research_mode == "quick"
    assert current.web_research_mode == "deep"
