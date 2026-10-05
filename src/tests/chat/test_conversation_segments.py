"""Chat owns conversation segments (PA-1.3, PA-2.2)."""
from __future__ import annotations

import uuid

import pytest

from app.platform.chat.segments import InMemoryConversationSegments


def _create(segments: InMemoryConversationSegments, session_id: str, **overrides):
    values = dict(
        session_id=session_id, interaction_mode="character", character_id="maya", profile_version=1,
        transcript_policy="persistent", read_memory=False, write_memory=False, shared_memory_access="none",
    )
    return segments.create_segment(**{**values, **overrides})


def test_segments_are_created_closed_and_read_back_in_order() -> None:
    session_id = f"chat:{uuid.uuid4().hex}"
    first = _create(InMemoryConversationSegments(), session_id)
    closed = InMemoryConversationSegments().close_segment(first.id)
    second = _create(InMemoryConversationSegments(), session_id, interaction_mode="system", character_id=None)

    loaded = InMemoryConversationSegments().segments(session_id)

    assert closed is not None and closed.ended_at is not None
    assert [segment.id for segment in loaded] == [first.id, second.id]
    assert loaded[0] == closed


def test_a_segment_identity_must_match_its_mode() -> None:
    with pytest.raises(ValueError, match="requires character_id"):
        _create(InMemoryConversationSegments(), "chat:x", character_id=None)
    with pytest.raises(ValueError, match="cannot have character_id"):
        _create(InMemoryConversationSegments(), "chat:x", interaction_mode="system")
