from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.gateway.tts_stream_contract import estimate_chat_stream_max_new_tokens
from app.live_speech.performance_contract import SpeechPerformancePlan


class FakeTtsProvider:
    provider_name = "fake"
    tts_capabilities = {
        "provider": "fake",
        "supports_streaming": True,
        "supports_concurrent_generation": False,
        "supports_emotion": False,
        "supports_speaking_rate": False,
        "supports_word_emphasis": False,
        "supports_ssml": False,
        "supports_word_timestamps": False,
    }

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate_audio_stream(self, **kwargs: Any):
        self.calls.append(kwargs)
        yield [0.25, -0.25] * 1_200, 24_000, {"chunk_index": 0}


class ExpressiveTtsProvider(FakeTtsProvider):
    provider_name = "expressive"
    tts_capabilities = {
        **FakeTtsProvider.tts_capabilities,
        "provider": "expressive",
        "supports_emotion": True,
        "supports_speaking_rate": True,
    }

    def build_performance_kwargs(self, _plan: SpeechPerformancePlan) -> dict[str, Any]:
        return {
            "emotion": "warm",
            "speaking_rate": 0.9,
            "emphasis": ["IMPORTANT"],
        }


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _request(
    text: str,
    phrase_index: int,
    *,
    delivery_plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stream_id = f"chat-live-test-p{phrase_index}"
    return {
        "type": "synthesize",
        "request_id": stream_id,
        "phrase_index": phrase_index,
        "text": text,
        "speaker": "Alex",
        "language": "English",
        "chunk_size": 8,
        "temperature": 0.6,
        "top_k": 20,
        "top_p": 0.85,
        "repetition_penalty": 1.0,
        "append_silence": False,
        "non_streaming_mode": False,
        "parity_mode": True,
        "diagnostics_stream_id": stream_id,
        **({"delivery_plan": delivery_plan} if delivery_plan else {}),
    }


def _plan() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "speech_act": "reassurance",
        "energy": "low",
        "warmth": "high",
        "certainty": "moderate",
        "pace": "slightly_slow",
        "clause_pause": "long",
        "emphasis": ["IMPORTANT"],
        "onset_policy": {
            "desired_perceived_onset_ms": 650,
            "maximum_additional_delay_ms": 350,
        },
        "nonverbal_eligibility": {
            "breath": True,
            "acknowledgement": True,
            "amused_exhale": False,
            "sigh": True,
        },
    }


def _assert_start_control(
    control: dict[str, Any],
    *,
    phrase_index: int,
    provider: str,
    applied: list[str],
    ignored: list[str],
) -> None:
    assert control == {
        "type": "start",
        "stream_id": f"chat-live-test-p{phrase_index}",
        "phrase_index": phrase_index,
        "sample_rate": 24_000,
        "sample_format": "pcm_s16le",
        "channels": 1,
        "frame_samples": 3_840,
        "diagnostics_log": "/tmp/tts-streaming.log",
        "provider_capabilities": {
            "provider": provider,
            "supports_streaming": True,
            "supports_concurrent_generation": False,
            "supports_emotion": provider == "expressive",
            "supports_speaking_rate": provider == "expressive",
            "supports_word_emphasis": False,
            "supports_ssml": False,
            "supports_word_timestamps": False,
        },
        "performance_controls_applied": applied,
        "performance_controls_ignored": ignored,
    }


def _configure_gateway(monkeypatch, provider: FakeTtsProvider):
    from app.gateway import tts_live_call_websocket

    logged_events: list[tuple[str, str, str, dict[str, Any]]] = []
    monkeypatch.setattr(tts_live_call_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(
        tts_live_call_websocket,
        "diagnostics_log_path",
        lambda: "/tmp/tts-streaming.log",
    )
    monkeypatch.setattr(
        tts_live_call_websocket,
        "stream_log",
        lambda stream_id, source, event, **details: logged_events.append(
            (stream_id, source, event, details)
        ),
    )
    monkeypatch.setattr(
        tts_live_call_websocket,
        "begin_stream",
        lambda stream_id, **details: 1,
    )
    monkeypatch.setattr(
        tts_live_call_websocket,
        "end_stream",
        lambda stream_id, **details: 0,
    )
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())
    return TestClient(app), logged_events


def test_live_call_websocket_reuses_one_connection_for_multiple_phrases(monkeypatch) -> None:
    provider = FakeTtsProvider()
    client, logged_events = _configure_gateway(monkeypatch, provider)

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(_request("First persistent phrase.", 0))
        first_start = websocket.receive_json()
        first_frame = websocket.receive_bytes()
        first_done = websocket.receive_json()
        websocket.send_json(
            {
                "type": "diagnostic",
                "stream_id": "chat-live-test-p0",
                "event": "playback_finished",
                "details": {"phrase_index": 0, "frames": 1},
            }
        )

        websocket.send_json(_request("Second persistent phrase.", 1))
        second_start = websocket.receive_json()
        second_frame = websocket.receive_bytes()
        second_done = websocket.receive_json()
        websocket.send_json({"type": "close", "reason": "finished"})

    _assert_start_control(
        first_start,
        phrase_index=0,
        provider="fake",
        applied=[],
        ignored=[],
    )
    _assert_start_control(
        second_start,
        phrase_index=1,
        provider="fake",
        applied=[],
        ignored=[],
    )
    assert len(first_frame) == 7_680
    assert len(second_frame) == 7_680
    assert first_done == {
        "type": "done",
        "stream_id": "chat-live-test-p0",
        "phrase_index": 0,
        "last_frame_index": 0,
        "partial": False,
    }
    assert second_done == {
        "type": "done",
        "stream_id": "chat-live-test-p1",
        "phrase_index": 1,
        "last_frame_index": 0,
        "partial": False,
    }

    assert [call["text"] for call in provider.calls] == [
        "First persistent phrase.",
        "Second persistent phrase.",
    ]
    assert all(call["parity_mode"] is False for call in provider.calls)
    assert all(call["repetition_penalty"] == 1.05 for call in provider.calls)
    assert [call["max_new_tokens"] for call in provider.calls] == [
        estimate_chat_stream_max_new_tokens("First persistent phrase."),
        estimate_chat_stream_max_new_tokens("Second persistent phrase."),
    ]

    request_events = [
        (stream_id, details.get("phrase_index"))
        for stream_id, _source, event, details in logged_events
        if event == "request_received"
    ]
    assert request_events == [("chat-live-test-p0", 0), ("chat-live-test-p1", 1)]
    event_names = [event for _stream_id, _source, event, _details in logged_events]
    assert event_names.count("done_control_sent") == 2
    assert event_names.count("phrase_route_cleanup") == 2
    assert "playback_finished" in event_names


def test_live_call_websocket_applies_only_declared_provider_controls(monkeypatch) -> None:
    provider = ExpressiveTtsProvider()
    client, logged_events = _configure_gateway(monkeypatch, provider)

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(
            _request(
                "This is IMPORTANT.",
                0,
                delivery_plan=_plan(),
            )
        )
        start = websocket.receive_json()
        websocket.receive_bytes()
        websocket.receive_json()
        websocket.send_json({"type": "close", "reason": "finished"})

    _assert_start_control(
        start,
        phrase_index=0,
        provider="expressive",
        applied=["emotion", "speaking_rate"],
        ignored=["emphasis"],
    )
    assert provider.calls[0]["emotion"] == "warm"
    assert provider.calls[0]["speaking_rate"] == 0.9
    assert "emphasis" not in provider.calls[0]
    provider_events = [
        details
        for _stream_id, _source, event, details in logged_events
        if event == "provider_resolved"
    ]
    assert provider_events[0]["performance_controls_applied"] == [
        "emotion",
        "speaking_rate",
    ]
    assert provider_events[0]["performance_controls_ignored"] == ["emphasis"]
