"""The gateway's link to the portrait service: opening it, and what it refuses to send (roadmap Phase 2)."""
from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

from app.conversation.portrait_stream_contract import pack, unpack
from app.platform.live_voice.portrait import link as link_module
from app.platform.live_voice.portrait.link import PortraitLink, PortraitUnavailable


@pytest.fixture(autouse=True)
def service_token(monkeypatch) -> None:
    monkeypatch.setenv("OMNIX_SERVICE_TOKEN", "t" * 43)


class FakeServiceSocket:
    def __init__(self, reply: Any) -> None:
        self.reply = reply
        self.sent: list[Any] = []
        self.closed = False

    async def send(self, message: Any) -> None:
        self.sent.append(message)

    async def recv(self) -> Any:
        if self.reply is None:
            await asyncio.sleep(10)  # the service never answers
        return self.reply

    async def close(self) -> None:
        self.closed = True


async def _open(socket: FakeServiceSocket) -> PortraitLink:
    async def connect(url: str, **kwargs: Any) -> FakeServiceSocket:
        return socket

    return await PortraitLink.open("http://portrait.test", call_key="c", principal="p", session="s",
                                   latent_key="k", emotion="neutral", on_frame=lambda frame: None,
                                   connect=connect)


@pytest.mark.parametrize("reply", [None, "not json", json.dumps(["ready"])])
def test_an_open_that_times_out_or_gets_a_bad_reply_closes_its_connection(monkeypatch, reply: Any) -> None:
    # Review finding (2026-10-31): only a refusal closed the connection; a timeout left it to the service's lease.
    monkeypatch.setattr(link_module, "OPEN_TIMEOUT_SECONDS", 0.05)
    socket = FakeServiceSocket(reply)
    with pytest.raises(PortraitUnavailable) as refused:
        asyncio.run(_open(socket))
    assert refused.value.code == "service_unreachable" and socket.closed


def test_a_refusal_closes_its_connection_and_says_why() -> None:
    socket = FakeServiceSocket(json.dumps({"type": "refused", "code": "portrait_busy", "message": "busy"}))
    with pytest.raises(PortraitUnavailable) as refused:
        asyncio.run(_open(socket))
    assert refused.value.code == "portrait_busy" and socket.closed


def test_a_pcm_block_whose_header_cannot_fit_is_dropped_not_raised() -> None:
    link = PortraitLink(FakeServiceSocket(None), on_frame=lambda frame: None)
    link.send_pcm("s" * 2_000, 0, b"\x00\x00")
    assert link.dropped == 1 and link._outbox.empty()


def test_a_long_segment_id_outside_the_basic_plane_still_packs() -> None:
    # 160 such characters were 1,920 bytes as \\u escapes, over the 1,024-byte header limit.
    segment = "\U0001F600" * 160
    header, payload = unpack(pack({"segment_id": segment, "offset": 0}, b"pcm"))
    assert header["segment_id"] == segment and payload == b"pcm"
