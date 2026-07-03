from __future__ import annotations

from app.live_speech.benchmark import benchmark_stt, benchmark_tts
from app.live_speech.compat import compatibility_payload
from app.live_speech.stt import BufferedStreamingTranscriber
from app.live_speech.tts import DeterministicSpeechSynthesizer


def _pcm_chunk() -> bytes:
    return (2000).to_bytes(2, byteorder="little", signed=True) * 3200


def test_benchmark_stt_reports_partial_and_final_timings() -> None:
    result = benchmark_stt(BufferedStreamingTranscriber(), [_pcm_chunk()], name="fake-stt")

    assert result.name == "fake-stt"
    assert result.first_transcript_delta_ms is not None
    assert result.final_transcript_ms is not None
    assert result.transcript == "transcribed speech"


def test_benchmark_tts_reports_first_audio_and_chunk_count() -> None:
    result = benchmark_tts(DeterministicSpeechSynthesizer(), "hello there", name="fake-tts")

    assert result.name == "fake-tts"
    assert result.first_audio_delta_ms is not None
    assert result.audio_chunk_count == 1


def test_compatibility_payload_lists_realtime_events() -> None:
    payload = compatibility_payload()

    assert payload["preferred_socket_path"] == "/v1/realtime"
    assert "input_audio_buffer.append" in payload["events"]["client_to_server"]
    assert "response.output_audio.delta" in payload["events"]["server_to_client"]
    assert "response.metrics" in payload["events"]["server_to_client"]
