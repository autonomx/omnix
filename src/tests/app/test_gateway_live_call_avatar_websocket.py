"""The live call's portrait websocket (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 2)."""
from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from app.platform.characters.avatar_models import CharacterAvatarPack
from app.platform.live_voice.portrait.link import PortraitUnavailable
from app.platform.live_voice.transport import avatar_websocket
from tests.app.test_gateway_tts_live_call_websocket import FakeTtsProvider, _configure_gateway, _request

STAMPS = {"created_at": "2026-10-30T00:00:00+00:00", "updated_at": "2026-10-30T00:00:00+00:00"}
PORTRAIT = CharacterAvatarPack(character_id="maya", renderer="portrait", base_asset_id="image:maya",
                               fallback_renderer="sprite", portrait_emotion="happy", **STAMPS)


class FakeLink:
    def __init__(self, on_frame) -> None:
        self.on_frame = on_frame
        self.sent: list[Any] = []
        self.closed = False

    def send(self, message: dict[str, Any]) -> None:
        self.sent.append(message)

    def send_pcm(self, segment_id: str, offset: int, pcm: bytes) -> None:
        self.sent.append(("pcm", segment_id, offset))

    async def close(self) -> None:
        self.closed = True


@pytest.fixture
def portrait(monkeypatch):
    """The portrait service and the session's avatar, replaced for the route under test."""
    opened: list[dict[str, Any]] = []
    state: dict[str, Any] = {"pack": PORTRAIT, "prepare_error": None}

    async def prepare(base_url: str, tenant: str, image: bytes) -> str:
        if state["prepare_error"]:
            raise state["prepare_error"]
        assert image == b"portrait bytes"
        return "latent-key"

    async def open_link(base_url: str, **kwargs: Any) -> FakeLink:
        link = FakeLink(kwargs["on_frame"])
        opened.append({**kwargs, "link": link})

        async def first_frame() -> None:
            await asyncio.sleep(0.05)
            await link.on_frame(b"frame-0")

        asyncio.get_running_loop().create_task(first_frame())
        return link

    monkeypatch.setattr(avatar_websocket, "portrait_url", lambda: "http://portrait.test")
    monkeypatch.setattr(avatar_websocket, "_load_session", lambda factory, session_id: SimpleNamespace(id=session_id))
    monkeypatch.setattr(avatar_websocket, "resolve_live_call_runtime",
                        lambda session: SimpleNamespace(avatar_pack=state["pack"]))
    monkeypatch.setattr(avatar_websocket, "default_character_avatar_service",
                        lambda: SimpleNamespace(portrait_image=lambda pack, max_bytes: b"portrait bytes"))
    monkeypatch.setattr(avatar_websocket, "prepare_portrait", prepare)
    monkeypatch.setattr(avatar_websocket.PortraitLink, "open", open_link)
    return SimpleNamespace(opened=opened, state=state)


def _avatar_url(token: str) -> str:
    return f"/api/tts/live-call/avatar-websocket?token={token}&session_id=chat-1"


def test_an_unknown_token_is_refused(monkeypatch, portrait) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with pytest.raises(WebSocketDisconnect) as closed:
        with client.websocket_connect(_avatar_url("not-a-token")) as websocket:
            websocket.receive_json()
    assert closed.value.code == 1008


@pytest.mark.parametrize(("setup", "code"), [
    (lambda monkeypatch, state: monkeypatch.setattr(avatar_websocket, "portrait_url", lambda: ""),
     "portrait_not_configured"),
    (lambda monkeypatch, state: state.update(pack=PORTRAIT.model_copy(update={"renderer": "sprite"})),
     "not_a_portrait"),
    (lambda monkeypatch, state: state.update(prepare_error=PortraitUnavailable("warming", "loading")), "warming"),
])
def test_a_call_whose_portrait_cannot_serve_is_told_why(monkeypatch, portrait, setup, code: str) -> None:
    setup(monkeypatch, portrait.state)
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token)) as avatar:
            reply = avatar.receive_json()
    assert reply["type"] == "unavailable" and reply["code"] == code


def test_the_portrait_attaches_to_the_call_relays_frames_and_play_positions(monkeypatch, portrait) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        hello = tts.receive_json()
        with client.websocket_connect(_avatar_url(hello["avatar_token"])) as avatar:
            assert avatar.receive_json() == {"type": "ready", "fallback_renderer": "sprite"}
            assert avatar.receive_bytes() == b"frame-0"
            opened = portrait.opened[0]
            assert (opened["call_key"], opened["latent_key"], opened["emotion"]) == (
                hello["call_key"], "latent-key", "happy")
            tts.send_json({**_request("Hello there.", 0), "output_id": "out", "generation_epoch": 1,
                           "segment_id": "seg"})
            tts.receive_json()
            tts.receive_bytes()
            tts.receive_json()
            avatar.send_json({"type": "frame_ack", "segment_id": "seg", "offset": 960})
            link = opened["link"]
            for _ in range(100):
                if any(isinstance(item, dict) and item.get("type") == "play_position" for item in link.sent):
                    break
                time.sleep(0.01)
        assert link.closed  # the avatar socket closed: its link is closed and detached
    copied = [item for item in link.sent if isinstance(item, tuple)]
    assert copied == [("pcm", "seg", 0)]
    assert {"type": "play_position", "segment_id": "seg", "offset": 960, "round_trip_seconds": 0.0} in link.sent
