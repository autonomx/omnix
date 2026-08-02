from __future__ import annotations

import asyncio
from array import array

import msgpack
import pytest

from app.providers.kyutai_live_stt import (
    KYUTAI_FRAME_SAMPLES,
    KyutaiLiveSttProvider,
    KyutaiLiveSttSession,
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

    def __aiter__(self) -> "FakeKyutaiSocket":
        return self

    async def __anext__(self) -> bytes:
        payload = await self.incoming.get()
        if payload is None:
            raise StopAsyncIteration
        return payload

    async def push(self, payload: dict[str, object]) -> None:
        await self.incoming.put(msgpack.packb(payload, use_bin_type=True))


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
        word = await anext(events)
        partial = await anext(events)
        word_end = await anext(events)

        assert endpoint.type == "endpoint_score"
        assert endpoint.probability is not None
        assert endpoint.fields == {"signal": "semantic_pause"}
        assert word.type == "word"
        assert word.text == "hello "
        assert word.start_ms == pytest.approx(400.0)
        assert partial.type == "partial"
        assert partial.text == "hello"
        assert word_end.type == "word_end"
        assert word_end.end_ms == pytest.approx(700.0)
        await session.close()

    asyncio.run(scenario())


def test_kyutai_flush_advances_delayed_model_state() -> None:
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
        assert result.realtime_factor >= 0.0
        await session.close()

    asyncio.run(scenario())


def test_kyutai_provider_rejects_unsupported_languages_before_connecting() -> None:
    async def scenario() -> None:
        provider = KyutaiLiveSttProvider(base_url="ws://unused")
        with pytest.raises(Exception, match="does not support language"):
            await provider.create_live_session(language="ja")

    asyncio.run(scenario())
