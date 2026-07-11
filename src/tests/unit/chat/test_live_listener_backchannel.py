from app.chat.live_conversation_proactive import stream_proactive_turn_chunks
from app.chat.models import ChatSession


def _session() -> ChatSession:
    return ChatSession(
        id="chat:one",
        title="Backchannel",
        message_count=0,
        messages=[],
        created_at="2026-07-11T00:00:00+00:00",
        updated_at="2026-07-11T00:00:00+00:00",
    )


def test_listener_backchannel_stream_does_not_require_provider() -> None:
    events = list(
        stream_proactive_turn_chunks(
            object(),
            _session(),
            initiative_reason="listener_backchannel:right",
        )
    )

    assert events[0]["type"] == "initiative"
    assert events[1] == {"type": "text_chunk", "text": "right"}
    assert events[2]["content"] == "right"
    assert events[2]["metadata"]["purpose"] == "listener_backchannel"
    assert events[2]["metadata"]["transient"] is True


def test_listener_backchannel_token_is_allowlisted() -> None:
    events = list(
        stream_proactive_turn_chunks(
            object(),
            _session(),
            initiative_reason="listener_backchannel:invented phrase",
        )
    )

    assert events[1]["text"] == "mhm"
