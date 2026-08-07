import struct

import pytest

from app.gateway.tts_stream_contract import (
    CHAT_STREAM_MAX_CODEC_CHUNK_STEPS,
    CHAT_STREAM_MIN_NEW_TOKENS,
    STREAM_MAX_INITIAL_SILENCE_MS,
    TtsStreamRequest,
    audio_chunk_to_pcm16_bytes,
    estimate_chat_stream_max_new_tokens,
    stream_pcm16_blocks,
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


def test_short_chat_clause_does_not_receive_eight_second_token_floor() -> None:
    text = "That works too"
    assert len(text) == 14
    assert CHAT_STREAM_MIN_NEW_TOKENS == 32
    assert estimate_chat_stream_max_new_tokens(text) == 40

    request = TtsStreamRequest.model_validate(
        {
            "text": text,
            "diagnostics_stream_id": "chat-live-short-tail",
            "max_new_tokens": 512,
        }
    )

    assert request.max_new_tokens == 40


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


def test_initial_silence_filter_falls_back_for_quiet_speech_within_bounded_audio() -> None:
    sample_rate = 24_000
    chunk_samples = 7_680
    silence = struct.pack("<h", 0) * chunk_samples
    quiet_speech = struct.pack("<h", 200) * chunk_samples

    blocks = list(
        stream_pcm16_blocks(
            iter(
                [
                    (silence, sample_rate, {"chunk": 0}),
                    (quiet_speech, sample_rate, {"chunk": 1}),
                ]
            ),
            block_samples=2_400,
        )
    )

    assert STREAM_MAX_INITIAL_SILENCE_MS == 400.0
    assert blocks
    first_samples = struct.unpack("<2400h", blocks[0][0])
    assert any(sample != 0 for sample in first_samples)
    assert blocks[0][2] == {"chunk": 1}


def test_initial_silence_filter_retains_preroll_until_real_signal_arrives() -> None:
    sample_rate = 24_000
    chunk_samples = 7_680
    silence = struct.pack("<h", 0) * chunk_samples
    extremely_quiet_speech = struct.pack("<h", 1) * chunk_samples

    blocks = list(
        stream_pcm16_blocks(
            iter(
                [
                    (silence, sample_rate, {"chunk": 0}),
                    (silence, sample_rate, {"chunk": 1}),
                    (extremely_quiet_speech, sample_rate, {"chunk": 2}),
                ]
            ),
            block_samples=2_400,
        )
    )

    assert blocks
    first_samples = struct.unpack("<2400h", blocks[0][0])
    assert any(sample != 0 for sample in first_samples)
    assert blocks[0][2] == {"chunk": 2}


def test_torch_tensor_pcm_conversion_avoids_python_scalar_fallback() -> None:
    torch = pytest.importorskip("torch")
    audio = torch.tensor(
        [[-1.0], [0.0], [1.0], [float("nan")], [float("inf")]],
        dtype=torch.float32,
    )

    pcm = audio_chunk_to_pcm16_bytes(audio)

    assert struct.unpack("<5h", pcm) == (-32767, 0, 32767, 0, 32767)
