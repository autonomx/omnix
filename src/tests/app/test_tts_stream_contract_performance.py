from __future__ import annotations

from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from app.gateway import tts_stream_contract
from app.gateway.tts_stream_contract import (
    TtsStreamRequest,
    audio_chunk_to_pcm16_bytes,
    initial_speech_start_byte,
)
from app.live_speech.performance_contract import (
    FASTER_QWEN3_TTS_CAPABILITIES,
    SpeechPerformancePlan,
    apply_performance_plan_to_provider,
    resolve_tts_provider_capabilities,
)


def _decode_pcm16(payload: bytes) -> list[int]:
    return np.frombuffer(payload, dtype="<i2").astype(np.int32).tolist()


def _performance_plan() -> SpeechPerformancePlan:
    return SpeechPerformancePlan(
        speech_act="reassurance",
        energy="low",
        warmth="high",
        certainty="moderate",
        pace="slightly_slow",
        clause_pause="long",
        emphasis=["IMPORTANT"],
        onset_policy={
            "desired_perceived_onset_ms": 650,
            "maximum_additional_delay_ms": 350,
        },
        nonverbal_eligibility={
            "breath": True,
            "acknowledgement": True,
            "amused_exhale": False,
            "sigh": True,
        },
    )


def test_typed_performance_plan_is_preserved_without_claiming_unsupported_provider_controls() -> None:
    request = TtsStreamRequest.model_validate(
        {
            "text": "Take your time.",
            "delivery_plan": _performance_plan().model_dump(mode="json"),
        }
    )

    assert request.delivery_plan is not None
    assert request.delivery_plan.schema_version == 1
    assert request.delivery_plan.speech_act == "reassurance"
    assert FASTER_QWEN3_TTS_CAPABILITIES.supports_streaming is True
    assert FASTER_QWEN3_TTS_CAPABILITIES.supports_emotion is False
    assert FASTER_QWEN3_TTS_CAPABILITIES.supports_speaking_rate is False
    assert FASTER_QWEN3_TTS_CAPABILITIES.supports_word_timestamps is False


def test_unknown_provider_uses_conservative_streaming_capabilities() -> None:
    class UnknownProvider:
        provider_name = "custom"

        def generate_audio_stream(self, **_kwargs: Any):
            yield from ()

    capabilities = resolve_tts_provider_capabilities(UnknownProvider())

    assert capabilities.provider == "custom"
    assert capabilities.supports_streaming is True
    assert capabilities.supports_emotion is False
    assert capabilities.supports_speaking_rate is False
    assert capabilities.supports_word_emphasis is False


def test_unsupported_provider_controls_are_ignored_explicitly() -> None:
    class QwenProvider:
        provider_name = "faster_qwen3_tts"

        def generate_audio_stream(self, **_kwargs: Any):
            yield from ()

        def build_performance_kwargs(self, _plan: SpeechPerformancePlan):
            return {
                "emotion": "warm",
                "speaking_rate": 0.9,
                "emphasis": ["IMPORTANT"],
                "unsupported": True,
            }

    application = apply_performance_plan_to_provider(
        QwenProvider(),
        _performance_plan(),
    )

    assert application.provider_kwargs == {}
    assert application.applied_controls == ()
    assert application.ignored_controls == (
        "pace",
        "energy",
        "warmth",
        "certainty",
        "emphasis",
    )


def test_declared_provider_mapper_only_applies_capability_allowed_kwargs() -> None:
    class ExpressiveProvider:
        provider_name = "expressive"
        tts_capabilities = {
            "provider": "expressive",
            "supports_streaming": True,
            "supports_concurrent_generation": False,
            "supports_emotion": True,
            "supports_speaking_rate": True,
            "supports_word_emphasis": False,
            "supports_ssml": False,
            "supports_word_timestamps": False,
        }

        def generate_audio_stream(self, **_kwargs: Any):
            yield from ()

        def build_performance_kwargs(self, _plan: SpeechPerformancePlan):
            return {
                "emotion": "warm",
                "speaking_rate": 0.9,
                "emphasis": ["IMPORTANT"],
                "unknown": "discarded",
            }

    application = apply_performance_plan_to_provider(
        ExpressiveProvider(),
        _performance_plan(),
    )

    assert application.provider_kwargs == {
        "emotion": "warm",
        "speaking_rate": 0.9,
    }
    assert application.applied_controls == ("emotion", "speaking_rate")
    assert application.ignored_controls == ("emphasis",)


def test_malformed_or_future_performance_plan_is_rejected() -> None:
    with pytest.raises(ValidationError):
        TtsStreamRequest.model_validate(
            {
                "text": "Hello.",
                "delivery_plan": {
                    "schema_version": 2,
                    "speech_act": "answer",
                    "unexpected": True,
                },
            }
        )


def test_audio_chunk_to_pcm16_bytes_vectorizes_clipping_and_non_finite_values() -> None:
    audio = np.asarray(
        [0.0, 0.5, -0.5, 1.0, -1.0, 2.0, -2.0, np.nan, np.inf, -np.inf],
        dtype=np.float32,
    )

    assert _decode_pcm16(audio_chunk_to_pcm16_bytes(audio)) == [
        0,
        16383,
        -16383,
        32767,
        -32767,
        32767,
        -32767,
        0,
        32767,
        -32767,
    ]


def test_audio_chunk_to_pcm16_bytes_uses_first_channel_for_multichannel_input() -> None:
    stereo = np.asarray([[0.25, 0.75], [-0.25, -0.75]], dtype=np.float32)

    assert _decode_pcm16(audio_chunk_to_pcm16_bytes(stereo)) == [8191, -8191]


def test_initial_speech_start_byte_preserves_configured_preroll() -> None:
    sample_rate = 1_000
    samples = np.zeros(200, dtype="<i2")
    samples[100] = 20_000

    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=sample_rate,
        threshold=0.01,
        preroll_ms=40.0,
    ) == 120


def test_initial_speech_start_byte_handles_negative_full_scale_without_overflow() -> None:
    samples = np.asarray([0, -32_768], dtype="<i2")

    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=24_000,
        threshold=0.5,
        preroll_ms=0.0,
    ) == 2


def test_initial_speech_start_byte_returns_none_for_silence() -> None:
    samples = np.zeros(64, dtype="<i2")

    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=24_000,
        threshold=0.01,
        preroll_ms=40.0,
    ) is None


def test_pcm_helpers_fall_back_when_numpy_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(tts_stream_contract, "np", None)

    assert _decode_pcm16(audio_chunk_to_pcm16_bytes([0.5, -0.5])) == [16383, -16383]
    samples = np.asarray([0, 20_000], dtype="<i2")
    assert initial_speech_start_byte(
        samples.tobytes(),
        sample_rate=24_000,
        threshold=0.01,
        preroll_ms=0.0,
    ) == 2


def test_first_canonical_phrase_uses_two_codec_steps() -> None:
    assert (
        tts_stream_contract.chat_stream_codec_chunk_cap(
            "conversation-chat-session-g7-p0"
        )
        == 2
    )
    assert (
        tts_stream_contract.chat_stream_codec_chunk_cap(
            "conversation-chat-session-g7-p1"
        )
        == 4
    )
    assert tts_stream_contract.chat_stream_codec_chunk_cap(None) == 4


def test_chat_stream_request_caps_only_the_first_phrase_to_two_codec_steps() -> None:
    first = TtsStreamRequest.model_validate(
        {
            "text": "Hello there.",
            "diagnostics_stream_id": "chat-live-test",
            "output_id": "conversation-chat-session-g8-p0",
            "chunk_size": 12,
        }
    )
    later = TtsStreamRequest.model_validate(
        {
            "text": "And the next sentence.",
            "diagnostics_stream_id": "chat-live-test",
            "output_id": "conversation-chat-session-g8-p1",
            "chunk_size": 12,
        }
    )

    assert first.chunk_size == 2
    assert later.chunk_size == 4
