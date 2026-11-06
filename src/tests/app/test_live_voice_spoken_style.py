from __future__ import annotations

from app.platform.chat.context_budget import PromptBudgetDiagnostics, estimate_tokens
from app.platform.chat.prompt_rendering import RenderedPrompt, RenderedPromptMessage
from app.providers.base import ChatMessage
from app.providers.claude_cli_provider import split_messages
from app.platform.live_voice.prompt.spoken_style import (
    LIVE_VOICE_NO_NARRATION_REMINDER,
    LIVE_VOICE_SPOKEN_STYLE,
    apply_live_voice_spoken_style,
    live_voice_turn_reminder,
)
from app.conversation.live_profile import LiveConversationProfile


def _rendered_prompt() -> RenderedPrompt:
    return RenderedPrompt(
        messages=[
            RenderedPromptMessage(role="system", content="You are Maya."),
            RenderedPromptMessage(role="user", content="How does the upgrade feel?"),
        ],
        diagnostics=PromptBudgetDiagnostics(
            estimated_tokens=8,
            usable_input_tokens=1_000,
            section_tokens={"system": 4, "user": 4},
        ),
    )


def test_spoken_style_is_inserted_after_leading_system_context() -> None:
    rendered = apply_live_voice_spoken_style(_rendered_prompt())

    assert [message.role for message in rendered.messages] == ["system", "system", "system", "user"]
    assert rendered.messages[1].content == LIVE_VOICE_SPOKEN_STYLE
    assert rendered.messages[2].content == live_voice_turn_reminder()
    assert rendered.messages[2].content.endswith(LIVE_VOICE_NO_NARRATION_REMINDER)
    assert rendered.messages[-1].content == "How does the upgrade feel?"
    assert rendered.diagnostics.section_tokens["live_voice_spoken_style"] == estimate_tokens(
        LIVE_VOICE_SPOKEN_STYLE
    ) + estimate_tokens(live_voice_turn_reminder())


def test_spoken_style_stays_before_rolling_conversation_history() -> None:
    rendered = RenderedPrompt(
        messages=[
            RenderedPromptMessage(role="system", content="You are Sofia."),
            RenderedPromptMessage(role="system", content="Approved memory."),
            RenderedPromptMessage(role="user", content="Earlier question"),
            RenderedPromptMessage(role="assistant", content="Earlier answer"),
            RenderedPromptMessage(role="user", content="Current question"),
        ],
        diagnostics=PromptBudgetDiagnostics(
            estimated_tokens=20,
            usable_input_tokens=1_000,
            section_tokens={},
        ),
    )

    apply_live_voice_spoken_style(rendered)

    roles = [message.role for message in rendered.messages]
    assert roles == ["system", "system", "system", "system", "user", "assistant", "user"]
    assert rendered.messages[2].content == LIVE_VOICE_SPOKEN_STYLE
    first_turn_index = next(
        index for index, message in enumerate(rendered.messages) if message.role in {"user", "assistant"}
    )
    assert all(message.role == "system" for message in rendered.messages[:first_turn_index])


def test_spoken_style_rejects_roleplay_copy() -> None:
    normalized = LIVE_VOICE_SPOKEN_STYLE.casefold()

    assert "ordinary conversational language" in normalized
    assert "literal words the character says aloud" in normalized
    assert "not a screenplay" in normalized
    assert "soft pause" in normalized
    assert "typing sounds implied" in normalized
    assert "do not spell out laughter" in normalized
    assert "do not use markdown emphasis or emoji" in normalized
    assert "easy to follow aloud" in normalized
    assert "customer-service phrasing" in normalized
    assert "never stack fillers" in normalized
    assert "attempt to sound human" in normalized
    assert "do not end every response with a question" in normalized


def test_the_chosen_response_length_replaces_the_one_fixed_length_rule() -> None:
    # The setting was saved but never read, and a fixed "longer responses are welcome" rule decided every length.
    brief = live_voice_turn_reminder(LiveConversationProfile(response_length="brief"))
    conversational = live_voice_turn_reminder(LiveConversationProfile(response_length="conversational"))
    detailed = live_voice_turn_reminder(LiveConversationProfile(response_length="detailed"))

    assert "one or two sentences" in brief and "longer responses are welcome" not in brief.casefold()
    assert "a few sentences" in conversational and "longer responses are welcome" not in conversational.casefold()
    assert "Longer responses are welcome" in detailed and "do not force every reply into a brief summary" in detailed
    assert "longer responses are welcome" not in LIVE_VOICE_SPOKEN_STYLE.casefold()
    assert conversational == live_voice_turn_reminder()  # the setting's default


def test_stance_and_talkativeness_are_said_only_when_they_ask_for_something() -> None:
    plain = live_voice_turn_reminder(LiveConversationProfile())

    listen = live_voice_turn_reminder(LiveConversationProfile(conversation_stance="listen"))
    advise = live_voice_turn_reminder(LiveConversationProfile(conversation_stance="advise"))
    quiet = live_voice_turn_reminder(LiveConversationProfile(talkativeness=30))
    chatty = live_voice_turn_reminder(LiveConversationProfile(talkativeness=70))
    middle = [live_voice_turn_reminder(LiveConversationProfile(talkativeness=value)) for value in (35, 50, 65)]

    assert "They want to be heard" in listen and "They want to be heard" not in plain
    assert "give a clear recommendation" in advise
    assert "Say little: let them lead" in quiet and "Say little" not in plain
    assert "Be forthcoming" in chatty and "Be forthcoming" not in plain
    assert all(reminder == plain for reminder in middle)  # the setting's "Balanced" band adds nothing


def test_settings_go_with_the_turn_and_never_change_the_system_prompt() -> None:
    # The system prompt chooses the waiting process: a changed setting must not need a new one.
    brief = LiveConversationProfile(response_length="brief", conversation_stance="listen", talkativeness=20)
    systems = []
    for profile in (None, brief):
        rendered = apply_live_voice_spoken_style(_rendered_prompt(), profile)
        system, prompt = split_messages([
            ChatMessage(role=message.role, content=message.content, per_turn=message.per_turn)
            for message in rendered.messages
        ])
        systems.append(system)
        assert live_voice_turn_reminder(profile) in prompt

    assert systems[0] == systems[1]
    assert "one or two sentences" not in systems[1]


def test_the_no_narration_reminder_goes_with_the_turn_and_leaves_the_system_prompt_alone() -> None:
    # The system prompt chooses the waiting process, so it must stay the same from turn to turn.
    rendered = apply_live_voice_spoken_style(_rendered_prompt())
    system, prompt = split_messages([
        ChatMessage(role=message.role, content=message.content, per_turn=message.per_turn) for message in rendered.messages
    ])

    assert LIVE_VOICE_SPOKEN_STYLE in system
    assert LIVE_VOICE_NO_NARRATION_REMINDER not in system
    assert LIVE_VOICE_NO_NARRATION_REMINDER in prompt
    assert prompt.index(LIVE_VOICE_NO_NARRATION_REMINDER) < prompt.index("How does the upgrade feel?")


def test_a_phone_call_overrides_what_a_character_description_says_about_acting_things_out() -> None:
    assert "the person cannot see the character" in LIVE_VOICE_SPOKEN_STYLE
    assert "I stop." in LIVE_VOICE_SPOKEN_STYLE


def test_spoken_style_application_is_idempotent() -> None:
    rendered = _rendered_prompt()

    apply_live_voice_spoken_style(rendered)
    apply_live_voice_spoken_style(rendered, LiveConversationProfile(response_length="brief"))

    assert sum(message.content == LIVE_VOICE_SPOKEN_STYLE for message in rendered.messages) == 1
    assert len(rendered.messages) == 4
