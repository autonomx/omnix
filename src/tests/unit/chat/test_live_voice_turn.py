"""One meaning of a spoken live-call turn, shared by every live-voice decision."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.conversation.contracts import is_live_voice_message, is_live_voice_turn
from app.platform.chat.models import SendChatMessageRequest


def test_the_ids_the_browser_mints_mark_a_spoken_turn() -> None:
    request = SendChatMessageRequest(content="hello", live_voice_turn_id="voice-turn:7")

    assert is_live_voice_turn({"user_turn_id": request.user_turn_id})
    assert is_live_voice_turn({"speech_segment_id": request.speech_segment_id})


@pytest.mark.parametrize(
    "metadata",
    [
        {"speech_segment_id": "voice-segment:abc"},
        # The segment field exists only for speech, so its naming convention is not required.
        {"speech_segment_id": "segment-without-prefix"},
        {"user_turn_id": "voice-user-turn:abc"},
    ],
)
def test_a_speech_segment_or_a_voice_turn_id_marks_a_spoken_turn(metadata) -> None:
    assert is_live_voice_turn(metadata)
    assert is_live_voice_message(SimpleNamespace(metadata=metadata))


@pytest.mark.parametrize(
    "metadata",
    [{}, {"speech_segment_id": "  "}, {"user_turn_id": "typed-turn:abc"}, None, "voice-segment:abc"],
)
def test_a_typed_turn_or_missing_metadata_is_not_spoken(metadata) -> None:
    assert not is_live_voice_turn(metadata)
    assert not is_live_voice_message(SimpleNamespace(metadata=metadata))
    assert not is_live_voice_message(object())
