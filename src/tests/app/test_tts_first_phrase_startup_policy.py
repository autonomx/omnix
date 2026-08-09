from app.gateway.tts_stream_contract import (
    CHAT_STREAM_FIRST_PHRASE_CODEC_CHUNK_STEPS,
    CHAT_STREAM_MAX_CODEC_CHUNK_STEPS,
    TtsStreamRequest,
    chat_stream_codec_chunk_cap,
)


def test_first_conversation_phrase_uses_two_step_codec_startup() -> None:
    output_id = "conversation-chat-s1-g7-p0"
    request = TtsStreamRequest.model_validate(
        {
            "text": "First accepted response phrase.",
            "diagnostics_stream_id": "chat-live-session",
            "output_id": output_id,
            "chunk_size": 8,
        }
    )

    assert CHAT_STREAM_FIRST_PHRASE_CODEC_CHUNK_STEPS == 2
    assert chat_stream_codec_chunk_cap(output_id) == 2
    assert request.chunk_size == 2


def test_later_conversation_phrases_keep_four_step_codec_cap() -> None:
    output_id = "conversation-chat-s1-g7-p1"
    request = TtsStreamRequest.model_validate(
        {
            "text": "A later response phrase.",
            "diagnostics_stream_id": "chat-live-session",
            "output_id": output_id,
            "chunk_size": 8,
        }
    )

    assert CHAT_STREAM_MAX_CODEC_CHUNK_STEPS == 4
    assert chat_stream_codec_chunk_cap(output_id) == 4
    assert request.chunk_size == 4


def test_noncanonical_output_id_does_not_take_first_phrase_fast_path() -> None:
    request = TtsStreamRequest.model_validate(
        {
            "text": "Unowned live speech.",
            "diagnostics_stream_id": "chat-live-session",
            "output_id": "live-observation-p0",
            "chunk_size": 8,
        }
    )

    assert chat_stream_codec_chunk_cap(request.output_id) == 4
    assert request.chunk_size == 4
