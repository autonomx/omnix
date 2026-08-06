import struct

import pytest

from app.gateway.tts_stream_contract import (
    CHAT_STREAM_MAX_CODEC_CHUNK_STEPS,
    TtsStreamRequest,
    audio_chunk_to_pcm16_bytes,
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


def test_torch_tensor_pcm_conversion_avoids_python_scalar_fallback() -> None:
    torch = pytest.importorskip("torch")
    audio = torch.tensor(
        [[-1.0], [0.0], [1.0], [float("nan")], [float("inf")]],
        dtype=torch.float32,
    )

    pcm = audio_chunk_to_pcm16_bytes(audio)

    assert struct.unpack("<5h", pcm) == (-32767, 0, 32767, 0, 32767)
