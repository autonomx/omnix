from __future__ import annotations

import asyncio
from array import array

import msgpack
import pytest

import app.providers.kyutai_live_stt as kyutai_module
from app.providers.kyutai_live_stt import (
    KYUTAI_FRAME_SAMPLES,
    KyutaiLiveSttError,
    KyutaiLiveSttProvider,
    KyutaiLiveSttSession,
    _join_url,
    classify_kyutai_connect_exception,
    pcm16le_to_float32,
)


class FakeKyutaiSocket:
    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self.incoming: asyncio.Queue[bytes | None] = asyncio.Queue()
        self.closed = False

    async def send(self, payload: bytes) -> None:
        self.sent.append(payload)

    async def close(self) -> None:
        self.closed = True
        await self.incoming.put(None)

    def __aiter__(self) -> FakeKyutaiSocket:
        return self

    async def __anext__(self) -> bytes:
        payload = await self.incoming.get()
        if payload is None:
            raise StopAsyncIteration
        return payload

    async def push(self, payload: dict[str, object]) -> None:
        await self.incoming.put(msgpack.packb(payload, use_bin_type=True))


class FakeInvalidStatus(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"server rejected WebSocket connection: HTTP {status_code}")
        self.response = type("FakeResponse", (), {"status_code": status_code})()


class InvalidMessage(Exception):
    pass


def _pcm(samples: list[int]) -> bytes:
    return array("h", samples).tobytes()


def test_pcm16le_to_float32_normalizes_samples() -> None:
    assert pcm16le_to_float32(_pcm([-32_768, 0, 16_384, 32_767])) == pytest.approx(
        [-1.0, 0.0, 0.5, 32_767 / 32_768]
    )


def test_kyutai_session_frames_pcm_for_moshi_server() -> None:
    async def scenario() -> None:
        socket = FakeKyutaiSocket()
        session = KyutaiLiveSttSession(socket)

        await session.send_audio(_pcm([1_000] * (KYUTAI_FRAME_SAMPLES - 1)))
        assert socket.sent == []
        await session.send_audio(_pcm([1_000]))

        assert len(socket.sent) == 1
        payload = msgpack.unpackb(socket.sent[0], raw=False)
        assert payload["type"] == "Audio"
        assert len(payload["pcm"]) == KYUTAI_FRAME_SAMPLES
        assert payload["pcm"][0] == pytest.approx(1_000 / 32_768)
        await session.close()

    asyncio.run(scenario())


def test_kyutai_session_normalizes_words_and_endpoint_scores() -> None:
    async def scenario() -> None:
        socket = FakeKyutaiSocket()
        session = KyutaiLiveSttSession(socket)
        session._reader_task = asyncio.create_task(session._read_messages())
        events = session.events()

        for step in range(13):
            await socket.push({"type": "Step", "step_idx": step, "prs": [0.0, 0.0, 0.8]})
        await socket.push({"type": "Word", "text": "hello ", "start_time": 0.4})
        await socket.push({"type": "EndWord", "stop_time": 0.7})

        endpoint = await anext(events)
        partial = await anext(events)
        word = await anext(events)

        assert endpoint.type == "endpoint_score"
        assert endpoint.probability is not None
        assert endpoint.fields == {"signal": "semantic_pause"}
        assert partial.type == "partial"
        assert partial.text == "hello"
        assert word.type == "word"
        assert word.text == "hello "
        assert word.start_ms == pytest.approx(400.0)
        assert word.end_ms == pytest.approx(700.0)
        await session.close()

    asyncio.run(scenario())


def test_kyutai_flush_advances_delayed_model_state_and_reports_standard_rtf() -> None:
    async def scenario() -> None:
        socket = FakeKyutaiSocket()
        session = KyutaiLiveSttSession(socket, delay_seconds=0.16, flush_timeout_seconds=1.0)
        session._reader_task = asyncio.create_task(session._read_messages())

        flush_task = asyncio.create_task(session.flush("attempt-1"))
        for _ in range(100):
            if len(socket.sent) >= 3:
                break
            await asyncio.sleep(0)
        assert len(socket.sent) == 3

        for step in range(3):
            await socket.push({"type": "Step", "step_idx": step, "prs": [0.0, 0.0, 1.0]})
        result = await flush_task

        assert result.attempt_id == "attempt-1"
        assert result.model_ms == pytest.approx(160.0)
        assert result.wall_ms >= 0.0
        assert result.realtime_factor == pytest.approx(result.wall_ms / result.model_ms)
        await session.close()

    asyncio.run(scenario())


def test_kyutai_flush_can_be_cancelled_while_waiting_for_model_steps() -> None:
    async def scenario() -> None:
        socket = FakeKyutaiSocket()
        session = KyutaiLiveSttSession(socket, delay_seconds=0.16, flush_timeout_seconds=5.0)
        session._reader_task = asyncio.create_task(session._read_messages())

        flush_task = asyncio.create_task(session.flush("attempt-cancel"))
        for _ in range(100):
            if len(socket.sent) >= 3:
                break
            await asyncio.sleep(0)
        await session.cancel_flush("attempt-cancel")

        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(flush_task, timeout=0.2)
        await session.close()

    asyncio.run(scenario())


def test_pinned_moshi_worker_uses_root_websocket_endpoint() -> None:
    assert _join_url("ws://127.0.0.1:8090", "") == "ws://127.0.0.1:8090"
    assert _join_url("ws://127.0.0.1:8090/", "/") == "ws://127.0.0.1:8090"
    assert (
        _join_url("ws://127.0.0.1:8090", "/api/asr-streaming")
        == "ws://127.0.0.1:8090/api/asr-streaming"
    )
    assert (
        _join_url("ws://127.0.0.1:8090/api/asr-streaming", "/api/asr-streaming")
        == "ws://127.0.0.1:8090/api/asr-streaming"
    )


def test_provider_defaults_to_root_path_and_exposes_override() -> None:
    provider = KyutaiLiveSttProvider(base_url="ws://probe")
    overridden = KyutaiLiveSttProvider(base_url="ws://probe", path="/api/asr-streaming")

    assert provider.path == ""
    assert overridden.path == "/api/asr-streaming"

    async def scenario() -> None:
        health = await provider.health()
        override_health = await overridden.health()
        assert health["path"] == ""
        assert override_health["path"] == "/api/asr-streaming"

    asyncio.run(scenario())


def test_kyutai_provider_rejects_unsupported_languages_before_connecting() -> None:
    async def scenario() -> None:
        provider = KyutaiLiveSttProvider(base_url="ws://unused")
        with pytest.raises(KyutaiLiveSttError, match="does not support language") as caught:
            await provider.create_live_session(language="ja")
        assert caught.value.retryable is False

    asyncio.run(scenario())


def test_kyutai_provider_probe_reports_real_upstream_readiness(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        socket = FakeKyutaiSocket()
        session = KyutaiLiveSttSession(socket)

        async def fake_connect(*args: object, **kwargs: object) -> KyutaiLiveSttSession:
            return session

        monkeypatch.setattr(KyutaiLiveSttSession, "connect", fake_connect)
        provider = KyutaiLiveSttProvider(base_url="ws://probe")

        assert await provider.probe(language="en", max_age_seconds=0) is True
        health = await provider.health()
        assert health["upstream_ready"] is True
        assert health["state"] == "closed"
        assert health["last_error_code"] is None
        assert health["path"] == ""
        assert socket.closed is True

    asyncio.run(scenario())


def test_connect_exception_classifier_uses_status_and_transport_type() -> None:
    assert classify_kyutai_connect_exception(FakeInvalidStatus(404)) == "upstream_endpoint_not_found"
    assert classify_kyutai_connect_exception(FakeInvalidStatus(503)) == "upstream_service_unavailable"
    assert classify_kyutai_connect_exception(TimeoutError("deadline exceeded")) == "upstream_connect_timeout"
    assert classify_kyutai_connect_exception(OSError(111, "Connection refused")) == "upstream_connection_refused"
    assert (
        classify_kyutai_connect_exception(RuntimeError("did not receive a valid HTTP response"))
        == "upstream_protocol_error"
    )
    assert (
        classify_kyutai_connect_exception(
            InvalidMessage("connection closed while reading HTTP status line")
        )
        == "upstream_protocol_error"
    )


def test_provider_health_preserves_safe_connect_failure_details(monkeypatch: pytest.MonkeyPatch) -> None:
    async def scenario() -> None:
        async def fail_connect(*args: object, **kwargs: object) -> object:
            raise FakeInvalidStatus(404)

        monkeypatch.setattr(kyutai_module, "_connect_websocket", fail_connect)
        provider = KyutaiLiveSttProvider(base_url="ws://probe")

        assert await provider.probe(language="en", max_age_seconds=0) is False
        health = await provider.health()
        assert health["upstream_ready"] is False
        assert health["last_error_code"] == "upstream_endpoint_not_found"
        assert health["last_error_type"] == "FakeInvalidStatus"
        assert health["last_error_stage"] == "connect"
        assert health["path"] == ""

    asyncio.run(scenario())