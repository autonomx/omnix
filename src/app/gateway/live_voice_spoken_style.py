"""Add a natural spoken-conversation contract to live voice prompts only."""
from __future__ import annotations

from functools import wraps
from typing import Any

from app.chat.context_budget import estimate_tokens
from app.chat.prompt_rendering import RenderedPrompt, RenderedPromptMessage
from app.chat.prompt_store import ChatSessionStore as PromptChatSessionStore

_HOOK_SENTINEL = "_omnix_live_voice_spoken_style_installed"
_SECTION_NAME = "live_voice_spoken_style"

LIVE_VOICE_SPOKEN_STYLE = """This response will be spoken aloud in a live conversation.
Speak as the character in ordinary conversational language, not as an assistant writing polished copy.
Return only the literal words the character says aloud. The response is dialogue, not a screenplay, roleplay transcript, performance note, or description of delivery.
Never write actions, gestures, facial expressions, sound descriptions, tone labels, implied sounds, or production notes in parentheses, brackets, or asterisks. Do not write annotations such as "(soft pause)", "*chuckles*", "typing sounds implied", or "playful tone".
Do not spell out laughter, sighs, breaths, typing, or other sound effects. Do not use markdown emphasis or emoji.
Answer the user's actual point directly, then develop the answer for as long as the subject genuinely needs. Longer responses are welcome when they add useful detail; do not force every reply into a brief summary.
Use contractions, natural transitions, and complete spoken sentences. Keep longer answers coherent and easy to follow aloud rather than sounding like an essay, report, list of talking points, or scripted monologue.
Prefer simple, specific words over enthusiastic adjectives, poetic metaphors, therapy language, customer-service phrasing, or exaggerated validation.
Do not turn the user's wording into a story about your AI, circuits, programming, an upgrade, or an attempt to sound human unless that detail is genuinely necessary to answer them.
A single brief hesitation is fine only when the character is genuinely thinking. Never stack fillers such as "Hmm... Um...", and do not add filler to every reply.
Do not end every response with a question; ask one only when it moves the conversation forward."""


def _is_live_voice_message(user_message: Any) -> bool:
    metadata = getattr(user_message, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    speech_segment_id = str(metadata.get("speech_segment_id") or "").strip()
    user_turn_id = str(metadata.get("user_turn_id") or "").strip()
    return bool(speech_segment_id or user_turn_id.startswith("voice-user-turn:"))


def apply_live_voice_spoken_style(rendered: RenderedPrompt) -> RenderedPrompt:
    """Keep the live-only style instruction inside the stable leading context.

    Stateful LM Studio Responses can continue with only the new user input when
    every system message precedes the rolling user/assistant history. Placing
    this stable instruction immediately before the current user turn made an
    otherwise valid live prompt structurally non-continuable once history was
    present. Insert it after the existing leading system block instead.
    """
    if any(
        message.role == "system" and message.content == LIVE_VOICE_SPOKEN_STYLE
        for message in rendered.messages
    ):
        return rendered

    insertion_index = len(rendered.messages)
    for index, message in enumerate(rendered.messages):
        if message.role in {"user", "assistant"}:
            insertion_index = index
            break
    rendered.messages.insert(
        insertion_index,
        RenderedPromptMessage(role="system", content=LIVE_VOICE_SPOKEN_STYLE),
    )
    token_cost = estimate_tokens(LIVE_VOICE_SPOKEN_STYLE)
    rendered.diagnostics.estimated_tokens += token_cost
    rendered.diagnostics.section_tokens[_SECTION_NAME] = token_cost
    return rendered


def install_live_voice_spoken_style_hook() -> None:
    """Install after the live-voice latency-profile hook has assembled its prompt."""
    if getattr(PromptChatSessionStore, _HOOK_SENTINEL, False):
        return

    original_build_prompt = PromptChatSessionStore.build_provider_prompt

    @wraps(original_build_prompt)
    def patched_build_prompt(
        self: PromptChatSessionStore,
        session: Any,
        user_message: Any,
        context_items: list[dict[str, Any]] | None = None,
    ):
        assembly, rendered = original_build_prompt(
            self,
            session,
            user_message,
            context_items,
        )
        if _is_live_voice_message(user_message):
            apply_live_voice_spoken_style(rendered)
            assembly.diagnostics[_SECTION_NAME] = {
                "enabled": True,
                "tokens": rendered.diagnostics.section_tokens.get(_SECTION_NAME, 0),
            }
        return assembly, rendered

    PromptChatSessionStore.build_provider_prompt = patched_build_prompt
    setattr(PromptChatSessionStore, _HOOK_SENTINEL, True)


__all__ = [
    "LIVE_VOICE_SPOKEN_STYLE",
    "apply_live_voice_spoken_style",
    "install_live_voice_spoken_style_hook",
]
