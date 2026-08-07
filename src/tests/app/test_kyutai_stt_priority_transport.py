from __future__ import annotations

import asyncio
from typing import Any, cast

from fastapi import WebSocket

from app.providers.kyutai_stt_priority_transport import KyutaiPrioritySender


class _FakeWebSocket:
    pass


def test_partial_overtakes_coalesced_endpoint_telemetry() -> None:
    async def scenario() -> None:
        sent: list[dict[str, Any]] = []

        async def send_immediately(
            _websocket: WebSocket,
            _lock: asyncio.Lock,
            payload: dict[str, Any],
        ) -> bool:
            sent.append(dict(payload))
            return True

        sender = KyutaiPrioritySender(send_immediately, interval_ms=100)
        websocket = cast(WebSocket, _FakeWebSocket())
        lock = asyncio.Lock()

        await sender.send(websocket, lock, {"type": "endpoint_score", "probability": 0.72})
        await sender.send(websocket, lock, {"type": "endpoint_score", "probability": 0.94})
        await sender.send(websocket, lock, {"type": "endpoint_candidate", "probability": 0.94})
        assert sent == []

        await sender.send(websocket, lock, {"type": "partial", "text": "How are you?"})

        assert [item["type"] for item in sent] == [
            "partial",
            "endpoint_candidate",
            "endpoint_score",
        ]
        assert sent[-1]["probability"] == 0.94

    asyncio.run(scenario())


def test_endpoint_telemetry_eventually_flushes_without_a_partial() -> None:
    async def scenario() -> None:
        sent: list[dict[str, Any]] = []

        async def send_immediately(
            _websocket: WebSocket,
            _lock: asyncio.Lock,
            payload: dict[str, Any],
        ) -> bool:
            sent.append(dict(payload))
            return True

        sender = KyutaiPrioritySender(send_immediately, interval_ms=5)
        websocket = cast(WebSocket, _FakeWebSocket())
        lock = asyncio.Lock()

        await sender.send(websocket, lock, {"type": "endpoint_score", "probability": 0.81})
        await sender.send(websocket, lock, {"type": "endpoint_candidate", "probability": 0.81})
        await asyncio.sleep(0.02)

        assert [item["type"] for item in sent] == [
            "endpoint_candidate",
            "endpoint_score",
        ]

    asyncio.run(scenario())


def test_non_telemetry_messages_remain_lossless_and_immediate() -> None:
    async def scenario() -> None:
        sent: list[dict[str, Any]] = []

        async def send_immediately(
            _websocket: WebSocket,
            _lock: asyncio.Lock,
            payload: dict[str, Any],
        ) -> bool:
            sent.append(dict(payload))
            return True

        sender = KyutaiPrioritySender(send_immediately)
        websocket = cast(WebSocket, _FakeWebSocket())
        lock = asyncio.Lock()

        assert await sender.send(
            websocket,
            lock,
            {"type": "result_available", "text": "final"},
        )
        assert sent == [{"type": "result_available", "text": "final"}]

    asyncio.run(scenario())
