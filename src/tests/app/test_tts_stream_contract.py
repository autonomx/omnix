from app.gateway.tts_stream_contract import (
    CHAT_STREAM_MAX_CODEC_CHUNK_STEPS,
    TtsStreamRequest,
)


def test_chat_stream_caps_codec_chunk_steps_for_lower_first_audio_latency() -> None:
    request = TtsStreamRequest.model_validate(
        {
            "text": "A live response sentence.",
            "diagnostics_stream_id": "chat-live-session",
            "chunk_size": 8,
            "parity_mode": True,
            "max_new_tokens": 512,
        }
    )

    assert CHAT_STREAM_MAX_CODEC_CHUNK_STEPS == 4
    assert request.chunk_size == 4
    assert request.parity_mode is False
    assert request.max_new_tokens is not None
    assert request.max_new_tokens < 512


def test_non_chat_stream_preserves_requested_codec_chunk_steps() -> None:
    request = TtsStreamRequest.model_validate(
        {
            "text": "Long-form narration.",
            "diagnostics_stream_id": "audiobook-session",
            "chunk_size": 8,
            "parity_mode": True,
            "max_new_tokens": 512,
        }
    )

    assert request.chunk_size == 8
    assert request.parity_mode is True
    assert request.max_new_tokens == 512
