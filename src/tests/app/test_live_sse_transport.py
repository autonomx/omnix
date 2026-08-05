from __future__ import annotations

import asyncio

from starlette.responses import StreamingResponse

from app.gateway.live_sse_transport import install_live_sse_transport_hook


def _collect(response: StreamingResponse) -> list[bytes]:
    async def collect() -> list[bytes]:
        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            chunks.append(chunk if isinstance(chunk, bytes) else chunk.encode(response.charset))
        return chunks

    return asyncio.run(collect())


def test_event_stream_has_flush_preamble_and_anti_buffering_headers(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "2048")
    install_live_sse_transport_hook()

    response = StreamingResponse(
        iter(["data: first\n\n"]),
        media_type="text/event-stream",
    )
    chunks = _collect(response)

    assert len(chunks[0]) == 2048
    assert chunks[0].startswith(b":")
    assert chunks[0].endswith(b"\n\n")
    assert chunks[1] == b"data: first\n\n"
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["connection"] == "keep-alive"
    assert "no-cache" in response.headers["cache-control"]
    assert "no-transform" in response.headers["cache-control"]


def test_non_event_stream_is_not_modified(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "2048")
    install_live_sse_transport_hook()

    response = StreamingResponse(iter(["plain text"]), media_type="text/plain")
    chunks = _collect(response)

    assert chunks == [b"plain text"]
    assert "x-accel-buffering" not in response.headers


def test_event_stream_preamble_can_be_disabled(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SSE_FLUSH_PREAMBLE_BYTES", "0")
    install_live_sse_transport_hook()

    response = StreamingResponse(iter(["data: first\n\n"]), media_type="text/event-stream")
    chunks = _collect(response)

    assert chunks == [b"data: first\n\n"]
    assert response.headers["x-accel-buffering"] == "no"
