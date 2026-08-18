from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from app.gateway.main import create_gateway_app
from app.gateway.tts_live_call_startup_frame_policy import (
    TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES,
)


class FakeTtsProvider:
    provider_name = "full-duplex-fixture"
    tts_capabilities = {
        "provider": "full-duplex-fixture",
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
        yield [0.2, -0.2] * 1_200, 24_000, {"chunk_index": 0}


class EmptyJobStore:
    def list_events(self, after_id: int, limit: int):
        return []


def _item_request(output_id: str, generation_epoch: int, output_order: int) -> dict[str, Any]:
    stream_id = f"chat-live-acceptance-{output_id}"
    return {
        "type": "synthesize",
        "request_id": stream_id,
        "output_id": output_id,
        "generation_epoch": generation_epoch,
        "output_order": output_order,
        "segment_id": f"segment-{output_id}",
        "phrase_index": output_order,
        "text": "Deterministic fixture output.",
        "speaker": "Alex",
        "language": "English",
        "chunk_size": 8,
        "temperature": 0.2,
        "top_k": 20,
        "top_p": 0.85,
        "repetition_penalty": 1.0,
        "append_silence": False,
        "non_streaming_mode": False,
        "parity_mode": True,
        "diagnostics_stream_id": stream_id,
    }


def test_item_cancellation_preserves_unrelated_persistent_tts_output(monkeypatch) -> None:
    from app.gateway import tts_live_call_websocket

    provider = FakeTtsProvider()
    monkeypatch.setattr(tts_live_call_websocket, "get_tts_provider", lambda: provider)
    monkeypatch.setattr(tts_live_call_websocket, "diagnostics_log_path", lambda: "/tmp/live-acceptance.log")
    monkeypatch.setattr(tts_live_call_websocket, "stream_log", lambda *args, **kwargs: None)
    monkeypatch.setattr(tts_live_call_websocket, "begin_stream", lambda *args, **kwargs: 1)
    monkeypatch.setattr(tts_live_call_websocket, "end_stream", lambda *args, **kwargs: 0)
    client = TestClient(
        create_gateway_app(job_store_factory=lambda: EmptyJobStore()),
        raise_server_exceptions=False,
    )

    with client.websocket_connect("/api/tts/live-call/websocket") as websocket:
        websocket.send_json(
            {
                "type": "cancel",
                "output_id": "output-a",
                "generation_epoch": 1,
                "segment_id": "segment-output-a",
                "reason": "source_self_corrected",
            }
        )
        accepted = websocket.receive_json()
        assert accepted == {
            "type": "cancel_accepted",
            "output_id": "output-a",
            "generation_epoch": 1,
            "segment_id": "segment-output-a",
            "generated_through_frame": -1,
        }

        websocket.send_json(_item_request("output-a", 1, 0))
        cancelled = websocket.receive_json()
        assert cancelled["type"] == "cancelled"
        assert cancelled["output_id"] == "output-a"
        assert cancelled["generation_epoch"] == 1
        assert cancelled["generated_through_frame"] == -1

        websocket.send_json(_item_request("output-b", 1, 1))
        started = websocket.receive_json()
        frame = websocket.receive_bytes()
        completed = websocket.receive_json()
        websocket.send_json({"type": "close", "reason": "acceptance-complete"})

    assert started["type"] == "start"
    assert started["output_id"] == "output-b"
    assert started["generation_epoch"] == 1
    assert started["output_order"] == 1
    assert started["segment_id"] == "segment-output-b"
    assert len(frame) == TTS_LIVE_CALL_STARTUP_FRAME_SAMPLES * 2
    assert completed["type"] == "done"
    assert completed["output_id"] == "output-b"
    assert completed["generation_epoch"] == 1
    assert completed["last_frame_index"] == 0
    assert [call["text"] for call in provider.calls] == ["Deterministic fixture output."]


def test_material_reconnect_is_ordered_idempotent_and_rejects_gaps() -> None:
    from app.gateway.live_material_context import live_material_store

    session_id = "full-duplex-reconnect-acceptance"
    live_material_store.clear(session_id)
    app = create_gateway_app(job_store_factory=lambda: EmptyJobStore())

    with TestClient(app, raise_server_exceptions=False) as first_client:
        first = first_client.post(
            f"/api/chat/sessions/{session_id}/live/material",
            json={
                "segment_id": "segment-0",
                "sequence": 0,
                "text": "First deterministic fixture segment.",
                "response_policy": "observe",
                "task_contract_id": "editing",
                "task_contract_version": 2,
            },
        )
        assert first.status_code == 200
        assert first.json()["accepted_sequence"] == 0
        assert first.json()["context_version"] == 1

    with TestClient(app, raise_server_exceptions=False) as reconnected_client:
        second_payload = {
            "segment_id": "segment-1",
            "sequence": 1,
            "text": "Second deterministic fixture segment.",
            "response_policy": "observe",
            "task_contract_id": "editing",
            "task_contract_version": 2,
        }
        second = reconnected_client.post(
            f"/api/chat/sessions/{session_id}/live/material",
            json=second_payload,
        )
        assert second.status_code == 200
        assert second.json()["accepted_sequence"] == 1
        assert second.json()["context_version"] == 2

        duplicate = reconnected_client.post(
            f"/api/chat/sessions/{session_id}/live/material",
            json=second_payload,
        )
        assert duplicate.status_code == 200
        assert duplicate.json()["idempotent"] is True
        assert duplicate.json()["context_version"] == 2

        gap = reconnected_client.post(
            f"/api/chat/sessions/{session_id}/live/material",
            json={
                **second_payload,
                "segment_id": "segment-3",
                "sequence": 3,
                "text": "Gap fixture.",
            },
        )
        assert gap.status_code == 409
        assert gap.json()["detail"].startswith("segment_sequence_gap:expected=")

        snapshot = reconnected_client.get(
            f"/api/chat/sessions/{session_id}/live/material"
        )
        assert snapshot.status_code == 200
        assert snapshot.json()["accepted_sequence"] == 1
        assert snapshot.json()["exact_segment_count"] == 2

    live_material_store.clear(session_id)
