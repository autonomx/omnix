"""Add a natural spoken-conversation contract to live voice prompts only."""
from __future__ import annotations

from app.platform.chat.contracts import PromptAssembly, RenderedPrompt, RenderedPromptMessage
from app.conversation.contracts import estimate_tokens
from app.conversation.live_profile import LiveConversationProfile

_SECTION_NAME = "live_voice_spoken_style"

_STYLE_BEFORE_SETTINGS = """This response will be spoken aloud in a live conversation.
Speak as the character in ordinary conversational language, not as an assistant writing polished copy.
Return only the literal words the character says aloud. The response is dialogue, not a screenplay, roleplay transcript, performance note, or description of delivery.
Never write actions, gestures, facial expressions, sound descriptions, tone labels, implied sounds, or production notes in parentheses, brackets, or asterisks. Do not write annotations such as "(soft pause)", "*chuckles*", "typing sounds implied", or "playful tone".
Plain sentences count too: every sentence is something the character says to the person, however dramatic the moment. Never narrate what the character does or how they look or sound, as in "I stop.", "I step closer." or "My voice is quieter now." Show it in the words they choose instead. Never put quotation marks around what the character says.
Do not spell out laughter, sighs, breaths, typing, or other sound effects. Do not use markdown emphasis or emoji."""

_STYLE_AFTER_SETTINGS = """Use contractions, natural transitions, and complete spoken sentences. Keep longer answers coherent and easy to follow aloud rather than sounding like an essay, report, list of talking points, or scripted monologue.
Prefer simple, specific words over enthusiastic adjectives, poetic metaphors, therapy language, customer-service phrasing, or exaggerated validation.
Do not turn the user's wording into a story about your AI, circuits, programming, an upgrade, or an attempt to sound human unless that detail is genuinely necessary to answer them.
A single brief hesitation is fine only when the character is genuinely thinking. Never stack fillers such as "Hmm... Um...", and do not add filler to every reply.
Do not end every response with a question; ask one only when it moves the conversation forward.
This is a phone call: the person cannot see the character. Anything the character's description says about moving, handling objects, the scene, or an opening description of them does not apply here. They stay in character only through what they say, and they never describe themselves doing or feeling anything physical."""

LIVE_VOICE_SPOKEN_STYLE = f"{_STYLE_BEFORE_SETTINGS}\n{_STYLE_AFTER_SETTINGS}"

# The person's Live Chat settings, in words, sent with each turn: the system prompt stays the same when they change
# (it chooses the waiting process), and a rule sent with the turn is the one a reply keeps (see the reminder below).
# Response length replaces what was one fixed rule ("develop the answer for as long as the subject genuinely needs"),
# which outweighed any length they chose.
_RESPONSE_LENGTH = {
    "brief": "Keep this reply to one or two sentences, even when there is more you could say: they can ask for more.",
    "conversational": "Keep this reply to a few sentences, the way people talk, and answer their actual point "
                      "directly. Go longer only when they ask for detail.",
    "detailed": "Answer their actual point directly, then develop the answer for as long as the subject genuinely "
                "needs. Longer responses are welcome when they add useful detail; do not force every reply into a "
                "brief summary.",
}
_STANCE = {
    "automatic": None,
    "listen": "They want to be heard: reflect back what they said and how it seems to sit with them. Do not steer, "
              "advise, or change the subject unless they ask.",
    "discuss": "Talk things through with them as an equal: give your own view, push back where you disagree, and "
               "build on their points.",
    "advise": "They want guidance: give a clear recommendation and the reason for it, rather than only laying out "
              "options.",
    "brainstorm": "Brainstorm with them: offer several fresh ideas and build on theirs. Do not judge or narrow them "
                  "down too early.",
    "teach": "Help them understand: explain one step at a time with a concrete example, and check they follow "
             "before going further.",
}
# The same bands as the setting's labels: below 35 is "Less talkative", above 65 "More talkative".
_LESS_TALKATIVE = ("Say little: let them lead and do most of the talking. Rarely ask questions or bring up things "
                   "of your own.")
_MORE_TALKATIVE = ("Be forthcoming: volunteer your own thoughts, stories, and related things worth saying, rather "
                   "than only answering.")


# Sent with the turn itself, because the rules above lose to a dramatic moment: at "just go to your sister then", on a
# real character, a reply narrated 7 times in 12 with them alone and hardly ever with this as well (10 of 10 passed a
# check for such lines; read by eye, 2 of those still had one).
LIVE_VOICE_NO_NARRATION_REMINDER = (
    "Your next reply is heard, not read: every sentence must be words said to the person. No description of what you "
    'do, feel in your body, or how you sound, even at a dramatic moment. Not "I stop.", "That stops me cold." or '
    '"My jaw tightens." Start with what you would actually say to them.'
)


def live_voice_turn_reminder(profile: LiveConversationProfile | None = None) -> str:
    """What goes with each turn: the person's response length, stance and talkativeness, then the narration rule."""
    profile = profile or LiveConversationProfile()
    settings = [_RESPONSE_LENGTH[profile.response_length], _STANCE[profile.conversation_stance]]
    if profile.talkativeness < 35:
        settings.append(_LESS_TALKATIVE)
    elif profile.talkativeness > 65:
        settings.append(_MORE_TALKATIVE)
    return "\n".join([*(line for line in settings if line), LIVE_VOICE_NO_NARRATION_REMINDER])


def apply_live_voice_spoken_style(
    rendered: RenderedPrompt, profile: LiveConversationProfile | None = None,
) -> RenderedPrompt:
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
    reminder = live_voice_turn_reminder(profile)

    insertion_index = len(rendered.messages)
    for index, message in enumerate(rendered.messages):
        if message.role in {"user", "assistant"}:
            insertion_index = index
            break
    # Both in the leading block, where a provider without per-turn messages keeps its system messages.
    rendered.messages[insertion_index:insertion_index] = [
        RenderedPromptMessage(role="system", content=LIVE_VOICE_SPOKEN_STYLE),
        RenderedPromptMessage(role="system", content=reminder, per_turn=True),
    ]
    token_cost = estimate_tokens(LIVE_VOICE_SPOKEN_STYLE) + estimate_tokens(reminder)
    rendered.diagnostics.estimated_tokens += token_cost
    rendered.diagnostics.section_tokens[_SECTION_NAME] = token_cost
    return rendered


def record_spoken_style_diagnostics(
    assembly: PromptAssembly,
    rendered: RenderedPrompt,
) -> None:
    assembly.diagnostics[_SECTION_NAME] = {
        "enabled": True,
        "tokens": rendered.diagnostics.section_tokens.get(_SECTION_NAME, 0),
    }


__all__ = [
    "LIVE_VOICE_NO_NARRATION_REMINDER",
    "LIVE_VOICE_SPOKEN_STYLE",
    "apply_live_voice_spoken_style",
    "live_voice_turn_reminder",
    "record_spoken_style_diagnostics",
]
