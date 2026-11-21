"""The sound tags a live call offers: only the ones the call's voice has recorded clips for.

The offer is stable across a call's turns (the voice and its clips do not change mid-call), so the system prompt
still allows LM Studio to continue the previous response.
"""
from __future__ import annotations

from typing import Any

from app.conversation.sound_tags import SOUND_TAG_CUES
from app.prompts import prompt_template

SOUND_TAGS_PROMPT = prompt_template(
    "live_voice.sound_tags.prompt", "1",
    (
        "Sound tags. You may write one of these tags in a reply, and the call plays it as a real sound in your "
        "own voice:\n{tags}\n"
        "Use at most one in a reply, at the start of a sentence, and only when the feeling is really there; most "
        "replies need none. Write the tag exactly as shown. These tags are the only bracketed text you may write; "
        "every other rule against brackets, actions and written-out sounds still holds."
    ),
)

_TAG_MEANINGS = {
    "hmm": "[hmm] a thoughtful hum, when you are genuinely weighing something",
    "chuckle": "[chuckle] a short soft laugh, when something is actually funny",
    "sigh": "[sigh] a sigh, at something tiring or sad, or in relief",
}


def offered_sound_tags(profile: Any, voice_cues: frozenset[str]) -> tuple[str, ...]:
    """The tags to offer: none with emotional attunement off, else each tag whose clip the voice has."""
    if str(getattr(profile, "emotional_attunement", "subtle") or "subtle") == "off":
        return ()
    return tuple(tag for tag, cue in SOUND_TAG_CUES.items() if cue in voice_cues)


def sound_tags_prompt(tags: tuple[str, ...]) -> str:
    if not tags:
        return ""
    return SOUND_TAGS_PROMPT.format(tags="\n".join(f"- {_TAG_MEANINGS[tag]}" for tag in tags))


__all__ = ["SOUND_TAGS_PROMPT", "offered_sound_tags", "sound_tags_prompt"]
