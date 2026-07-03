from __future__ import annotations

from app.live_speech.benchmark_runner import run_benchmarks, sample_pcm_chunks
from app.live_speech.realtime import LiveSpeechRealtimeService
from app.live_speech.tts import DeterministicSpeechSynthesizer


def test_benchmark_runner_emits_targets_and_results() -> None:
    payload = run_benchmarks()

    assert payload["ok"] is True
    assert payload["targets_ms"]["first_transcript_delta"] == 500
    assert {item["name"] for item in payload["results"]} == {"live-speech-stt", "live-speech-tts"}


def test_sample_pcm_chunks_are_non_empty_and_deterministic() -> None:
    first = sample_pcm_chunks(chunks=2, samples_per_chunk=4)
    second = sample_pcm_chunks(chunks=2, samples_per_chunk=4)

    assert first == second
    assert len(first) == 2
    assert all(chunk for chunk in first)


def test_barge_in_cancels_active_response_generation() -> None:
    service = LiveSpeechRealtimeService()
    service.response_active = True
    service.response_id = "resp_active"
    generation_before = service.generation
    loud = (2000).to_bytes(2, byteorder="little", signed=True) * 3200

    events = service.append_audio(loud)

    assert service.generation == generation_before + 1
    event_types = [evt.type for evt in events]
    assert "input_audio_buffer.speech_started" in event_types
    assert "response.done" in event_types
    cancelled = [evt for evt in events if evt.type == "response.done"][-1]
    assert cancelled.payload["response"]["status"] == "cancelled"
    assert cancelled.payload["response"]["status_details"]["reason"] == "turn_detected"


def test_stale_audio_chunks_are_counted_after_cancel() -> None:
    service = LiveSpeechRealtimeService(synthesizer=DeterministicSpeechSynthesizer())
    generation = service.generation
    service.cancel_response()

    assert service.cancel_scope.should_drop(generation) is True
    service.metrics.drop_stale_chunk()
    assert service.metrics.stale_chunks_dropped == 1
