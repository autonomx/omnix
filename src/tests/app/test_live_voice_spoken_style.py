from __future__ import annotations

from app.chat.context_budget import PromptBudgetDiagnostics, estimate_tokens
from app.chat.prompt_rendering import RenderedPrompt, RenderedPromptMessage
from app.gateway.live_voice_spoken_style import (
    LIVE_VOICE_SPOKEN_STYLE,
    apply_live_voice_spoken_style,
)


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

    assert [message.role for message in rendered.messages] == ["system", "system", "user"]
    assert rendered.messages[1].content == LIVE_VOICE_SPOKEN_STYLE
    assert rendered.messages[-1].content == "How does the upgrade feel?"
    assert rendered.diagnostics.section_tokens["live_voice_spoken_style"] == estimate_tokens(
        LIVE_VOICE_SPOKEN_STYLE
    )


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
    assert roles == ["system", "system", "system", "user", "assistant", "user"]
    assert rendered.messages[2].content == LIVE_VOICE_SPOKEN_STYLE
    first_turn_index = next(
        index for index, message in enumerate(rendered.messages) if message.role in {"user", "assistant"}
    )
    assert all(message.role == "system" for message in rendered.messages[:first_turn_index])


def test_spoken_style_rejects_roleplay_copy_without_forcing_brevity() -> None:
    normalized = LIVE_VOICE_SPOKEN_STYLE.casefold()

    assert "ordinary conversational language" in normalized
    assert "literal words the character says aloud" in normalized
    assert "not a screenplay" in normalized
    assert "soft pause" in normalized
    assert "typing sounds implied" in normalized
    assert "do not spell out laughter" in normalized
    assert "do not use markdown emphasis or emoji" in normalized
    assert "longer responses are welcome" in normalized
    assert "do not force every reply into a brief summary" in normalized
    assert "easy to follow aloud" in normalized
    assert "customer-service phrasing" in normalized
    assert "never stack fillers" in normalized
    assert "attempt to sound human" in normalized
    assert "do not end every response with a question" in normalized
    assert "one to three short sentences" not in normalized


def test_spoken_style_application_is_idempotent() -> None:
    rendered = _rendered_prompt()

    apply_live_voice_spoken_style(rendered)
    apply_live_voice_spoken_style(rendered)

    assert sum(message.content == LIVE_VOICE_SPOKEN_STYLE for message in rendered.messages) == 1
