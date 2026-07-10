from __future__ import annotations

from app.assist_core.live_agent_router import (
    LiveAgentRuntimeConfig,
    classify_live_agent_intent,
    resolve_live_agent_route,
)


def _config(**changes) -> LiveAgentRuntimeConfig:
    return LiveAgentRuntimeConfig(
        enabled=True,
        auto_route_enabled=True,
        require_hermes=True,
        hermes_enabled=True,
        **changes,
    )


def test_live_agent_router_keeps_conversation_and_information_on_chat() -> None:
    for text in (
        "Hello",
        "How are you?",
        "Explain how the thermostat works",
        "What do you think about my schedule?",
        "I might update that later",
    ):
        task, _, _ = classify_live_agent_intent(text)
        assert task is False
        decision = resolve_live_agent_route(
            content=text,
            user_turn_id="voice-user-turn:1",
            config=_config(),
        )
        assert decision.route == "direct_chat"


def test_live_agent_router_routes_clear_live_actions_to_agent() -> None:
    for text in (
        "Turn off the kitchen light",
        "Can you schedule a meeting for tomorrow?",
        "Send an email to Alex",
        "Create a reminder for six",
        "Use the agent to update the repository issue",
    ):
        decision = resolve_live_agent_route(
            content=text,
            speech_segment_id="voice-segment:1",
            config=_config(),
        )
        assert decision.route == "agent_plan"
        assert decision.automatic is True
        assert decision.proposal_only is True
        assert decision.review_required is True
        assert decision.executes is False


def test_live_agent_router_is_disabled_and_hermes_independent_by_default() -> None:
    disabled = resolve_live_agent_route(
        content="Turn off the kitchen light",
        user_turn_id="voice-user-turn:1",
        config=LiveAgentRuntimeConfig(),
    )
    assert disabled.route == "direct_chat"
    assert disabled.reason == "live_agent_disabled"

    hermes_disabled = resolve_live_agent_route(
        content="Turn off the kitchen light",
        user_turn_id="voice-user-turn:1",
        config=_config(hermes_enabled=False),
    )
    assert hermes_disabled.route == "direct_chat"
    assert hermes_disabled.reason == "hermes_disabled"


def test_live_agent_auto_route_never_applies_to_normal_typed_chat() -> None:
    decision = resolve_live_agent_route(
        content="Delete the file",
        config=_config(),
    )
    assert decision.route == "direct_chat"
    assert decision.reason == "not_live_voice"


def test_explicit_agent_mode_preserves_existing_agent_entry_point() -> None:
    decision = resolve_live_agent_route(
        content="Plan this task",
        agent_mode=True,
        config=LiveAgentRuntimeConfig(),
    )
    assert decision.route == "agent_plan"
    assert decision.automatic is False
    assert decision.reason == "explicit_agent_mode"
