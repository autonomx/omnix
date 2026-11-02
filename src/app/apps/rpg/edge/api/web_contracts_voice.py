"""What the RPG web client reads from the voice routes (EV-13); see ``web_contracts``."""
from __future__ import annotations

from typing_extensions import NotRequired, Required, TypedDict


class RpgVoiceCastEntry(TypedDict, total=False):
    """The narrator or a person who speaks, and their voice (EV-13)."""

    speaker_id: Required[str]
    name: Required[str]
    voice_id: NotRequired[str]
    voice_revision: NotRequired[str]
    chosen_by: NotRequired[str]


class RpgCastableVoice(TypedDict, total=False):
    voice_id: Required[str]
    name: Required[str]
    description: Required[str]


class RpgVoiceCastResponse(TypedDict, total=False):
    ok: Required[bool]
    session_id: Required[str]
    cast: Required[list[RpgVoiceCastEntry]]
    voices: Required[list[RpgCastableVoice]]


class RpgSpeechSegment(TypedDict):
    speaker_id: str
    voice_id: str
    sentences: list[str]


class RpgSpeechPlanResponse(TypedDict, total=False):
    ok: Required[bool]
    session_id: Required[str]
    segments: Required[list[RpgSpeechSegment]]
