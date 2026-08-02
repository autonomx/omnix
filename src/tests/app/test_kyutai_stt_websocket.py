from __future__ import annotations

import asyncio
import base64
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.providers.kyutai_stt_websocket import install_kyutai_stt_websocket
from app.providers.live_stt_contracts import (
    CAP_AUTHORITATIVE_FINAL,
    CAP_CLIENT_AUDIO_REPLAY,
    CAP_CONTINUOUS_WORDS,
    CAP_DELAYED_FLUSH,
    CAP_SEMANTIC_ENDPOINTING,
    CAP_WORD_TIMESTAMPS,
    LiveSttEvent,
    LiveSttFlushResult,
    LiveSttNegotiation,
)


class FakeLiveSession:
    negotiation = LiveSttNegotiation(
        provider="kyutai",
        protocol="segmented-v1",
        sample_rate=24_000,
        frame_samples=1_920,
        capabilities=frozenset(
            {
                CAP_AUTHORITATIVE_FINAL,
                CAP_CLIENT_AUDIO_REPLAY,
                CAP_CONTINUOUS_WORDS,
                CAP_DELAYED_FLUSH,
                CAP_SEMANTIC_ENDPOINTING,
                CAP_WORD_TIMESTAMPS,
            }
        ),
    )

    def __init__(self, *, block_flush: bool = False) -> None:
        self.sent_audio: list[bytes] = []
        self.transcript = ""
        self.block_flush = block_flush
        self.cancelled: set[str] = set()
        self._events: asyncio.Queue[LiveSttEvent | None] = asyncio.Queue()

    async def send_audio(self, pcm16le: bytes) -> None:
        self.sent_audio.append(pcm16le)
        self.transcript = "hello"
        await self._events.put(LiveSttEvent(type="partial", text=self.transcript))
        await self._events.put(
            LiveSttEvent(type="word", text="hello", start_ms=10.0, end_ms=210.0)
        )

    async def flush(self, attempt_id: str) -> LiveSttFlushResult:
        await self._events.put(LiveSttEvent(type="flush_started", attempt_id=attempt_id))
        if self.block_flush:
            while attempt_id not in self.cancelled:
                await asyncio.sleep(0.005)
            raise asyncio.CancelledError
        await self._events.put(
            LiveSttEvent(
                type="flush_completed",
                attempt_id=attempt_id,
                fields={"wall_ms": 50.0, "model_ms": 500.0, "realtime_factor": 0.1},
            )
        )
        return LiveSttFlushResult(
            attempt_id=attempt_id,
            transcript=self.transcript,
            wall_ms=50.0,
            model_ms=500.0,
            realtime_factor=0.1,
        )

    async def cancel_flush(self, attempt_id: str) -> None:
        self.cancelled.add(attempt_id)
        await self._events.put(LiveSttEvent(type="flush_cancelled", attempt_id=attempt_id))

    async def events(self) -> AsyncIterator[LiveSttEvent]:
        while True:
            event = await self._events.get()
            if event is None:
                return
            yield event

    async def close(self) -> None:
        await self._events.put(None)


@dataclass
class FakeProvider:
    block_flush: bool = False

    def __post_init__(self) -> None:
        self.sessions: list[FakeLiveSession] = []
        self.failures: list[tuple[str, bool]] = []

    async def create_live_session(self, *, language: str | None = None) -> FakeLiveSession:
        assert language in {"en", "fr"}
        session = FakeLiveSession(block_flush=self.block_flush)
        self.sessions.append(session)
        return session

    def record_runtime_failure(self, message: str, *, retryable: bool = True) -> None:
        self.failures.append((message, retryable))

    async def health(self) -> Mapping[str, Any]:
        return {"state": "closed"}


def _audio_message(session_id: str, capture_epoch: str, segment_id: str = "segment-0") -> dict[str, Any]:
    payload = base64.b64encode(b"\x01\x00\x02\x00").decode("ascii")
    return {
        "type": "audio",
        "protocol": "segmented-v1",
        "sessionId": session_id,
        "captureEpoch": capture_epoch,
        "segmentId": segment_id,
        "sequence": 0,
        "captureStartSample": 0,
        "primaryStartSample": 0,
        "sampleStart": 0,
        "sampleEnd": 2,
        "sampleRate": 24_000,
        "data": payload,
    }


def _open_socket(provider: FakeProvider):
    app = FastAPI()
    install_kyutai_stt_websocket(app, provider=provider)  # type: ignore[arg-type]
    client = TestClient(app)
    return client, client.websocket_connect("/ws/transcribe?language=en")


def test_bridge_forwards_words_and_publishes_normalized_result() -> None:
    provider = FakeProvider()
    client, connection = _open_socket(provider)
    with client, connection as websocket:
        ready = websocket.receive_json()
        assert ready["provider"] == "kyutai"
        assert "client_audio_replay" in ready["capabilities"]
        assert ready["language"] == "en"

        session_id = "session-1"
        capture_epoch = "capture-1"
        websocket.send_json(
            {
                "type": "hello",
                "sessionId": session_id,
                "captureEpoch": capture_epoch,
                "sampleRate": 24_000,
            }
        )
        assert websocket.receive_json()["type"] == "session_ready"
        websocket.send_json(_audio_message(session_id, capture_epoch))
        assert websocket.receive_json()["type"] == "audio_buffered"

        seen_types: set[str] = set()
        while not {"partial", "word"}.issubset(seen_types):
            seen_types.add(websocket.receive_json()["type"])

        websocket.send_json(
            {
                "type": "finalize",
                "sessionId": session_id,
                "captureEpoch": capture_epoch,
                "segmentId": "segment-0",
                "sequence": 0,
                "finalizeRequestId": "flush-1",
                "endSample": 2,
            }
        )
        messages: list[dict[str, Any]] = []
        while not any(message.get("type") == "result_available" for message in messages):
            messages.append(websocket.receive_json())

        result = next(message for message in messages if message["type"] == "result_available")
        assert result["text"] == "hello"
        assert result["provider"] == "kyutai"
        assert result["providerMetrics"]["flushRealtimeFactor"] == 0.1


def test_bridge_reads_cancel_flush_while_worker_is_flushing() -> None:
    provider = FakeProvider(block_flush=True)
    client, connection = _open_socket(provider)
    with client, connection as websocket:
        websocket.receive_json()
        session_id = "session-cancel"
        capture_epoch = "capture-cancel"
        websocket.send_json(
            {
                "type": "hello",
                "sessionId": session_id,
                "captureEpoch": capture_epoch,
                "sampleRate": 24_000,
            }
        )
        websocket.receive_json()
        websocket.send_json(_audio_message(session_id, capture_epoch))
        websocket.receive_json()
        while websocket.receive_json()["type"] != "word":
            pass
        websocket.send_json(
            {
                "type": "finalize",
                "sessionId": session_id,
                "captureEpoch": capture_epoch,
                "segmentId": "segment-0",
                "sequence": 0,
                "finalizeRequestId": "flush-cancel",
                "endSample": 2,
            }
        )

        message_types: set[str] = set()
        while "flush_started" not in message_types:
            message_types.add(websocket.receive_json()["type"])
        websocket.send_json({"type": "cancel_flush", "attemptId": "flush-cancel"})
        while not {"flush_cancelled", "segment_error"}.issubset(message_types):
            message_types.add(websocket.receive_json()["type"])

        assert "flush-cancel" in provider.sessions[0].cancelled


def test_bridge_rejects_oversized_audio_frames_without_reaching_provider() -> None:
    provider = FakeProvider()
    client, connection = _open_socket(provider)
    with client, connection as websocket:
        websocket.receive_json()
        websocket.send_json(
            {
                "type": "hello",
                "sessionId": "session-large",
                "captureEpoch": "capture-large",
                "sampleRate": 24_000,
            }
        )
        websocket.receive_json()
        message = _audio_message("session-large", "capture-large")
        message["data"] = base64.b64encode(bytes(24_000 * 2 * 2 + 2)).decode("ascii")
        websocket.send_json(message)
        error = websocket.receive_json()

        assert error["type"] == "segment_error"
        assert error["errorCode"] == "audio_frame_limit"
        assert provider.sessions[0].sent_audio == []
