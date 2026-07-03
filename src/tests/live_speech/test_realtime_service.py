from __future__ import annotations

import base64

from app.live_speech.protocol import dispatch_client_event
from app.live_speech.realtime import LiveSpeechRealtimeService


def _loud_pcm(samples: int = 3200) -> bytes:
    sample = (2000).to_bytes(2, byteorder="little", signed=True)
    return sample * samples


def test_audio_append_emits_speech_started_and_transcript_delta() -> None:
    service = LiveSpeechRealtimeService()
    audio = base64.b64encode(_loud_pcm()).decode("ascii")

    events = dispatch_client_event(service, {"type": "input_audio_buffer.append", "audio": audio})
    event_types = [evt.type for evt in events]

    assert "input_audio_buffer.speech_started" in event_types
    assert "conversation.item.input_audio_transcription.delta" in event_types
    assert service.last_transcript.startswith("listening")


def test_response_create_streams_text_audio_metrics_and_done() -> None:
    service = LiveSpeechRealtimeService()
    dispatch_client_event(
        service,
        {
            "type": "conversation.item.create",
            "item": {"type": "input_text", "text": "hello there"},
        },
    )

    events = dispatch_client_event(service, {"type": "response.create"})
    event_types = [evt.type for evt in events]

    assert event_types[0] == "response.created"
    assert "response.text.delta" in event_types
    assert "response.output_audio.delta" in event_types
    assert "response.metrics" in event_types
    assert event_types[-1] == "response.done"
    assert events[-1].payload["response"]["status"] == "completed"


def test_cancel_response_increments_generation_and_marks_cancelled() -> None:
    service = LiveSpeechRealtimeService()
    service.response_active = True
    service.response_id = "resp_test"
    generation_before = service.generation

    events = dispatch_client_event(service, {"type": "response.cancel"})

    assert service.generation == generation_before + 1
    assert events[-1].type == "response.done"
    assert events[-1].payload["response"]["status"] == "cancelled"
    assert events[-1].payload["response"]["status_details"]["reason"] == "client_cancelled"


def test_session_update_deep_merges_turn_detection() -> None:
    service = LiveSpeechRealtimeService()

    events = dispatch_client_event(
        service,
        {
            "type": "session.update",
            "session": {"turn_detection": {"threshold": 0.02}, "voice": "Aiden"},
        },
    )

    assert service.config.turn_detection.threshold == 0.02
    assert service.config.turn_detection.silence_duration_ms == 500
    assert service.config.voice == "Aiden"
    assert events[0].type == "session.updated"
