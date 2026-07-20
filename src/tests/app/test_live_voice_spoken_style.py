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


def test_spoken_style_is_inserted_before_the_current_user_turn() -> None:
    rendered = apply_live_voice_spoken_style(_rendered_prompt())

    assert [message.role for message in rendered.messages] == ["system", "system", "user"]
    assert rendered.messages[-2].content == LIVE_VOICE_SPOKEN_STYLE
    assert rendered.messages[-1].content == "How does the upgrade feel?"
    assert rendered.diagnostics.section_tokens["live_voice_spoken_style"] == estimate_tokens(
        LIVE_VOICE_SPOKEN_STYLE
    )


def test_spoken_style_explicitly_rejects_assistant_copy_patterns() -> None:
    normalized = LIVE_VOICE_SPOKEN_STYLE.casefold()

    assert "ordinary conversational language" in normalized
    assert "polished copy" in normalized
    assert "customer-service phrasing" in normalized
    assert "do not end every response with a question" in normalized
    assert "circuits" in normalized


def test_spoken_style_application_is_idempotent() -> None:
    rendered = _rendered_prompt()

    apply_live_voice_spoken_style(rendered)
    apply_live_voice_spoken_style(rendered)

    assert sum(message.content == LIVE_VOICE_SPOKEN_STYLE for message in rendered.messages) == 1
