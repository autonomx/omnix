"""The live call's portrait websocket (roadmap: docs/architecture/OMNIX_LIVE_PORTRAIT_ROADMAP.md, Phase 2)."""
from __future__ import annotations

import asyncio
import contextlib
import time
from types import SimpleNamespace
from typing import Any

import pytest
from starlette.websockets import WebSocketDisconnect

from app.conversation.portrait_stream_contract import pack
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
    state: dict[str, Any] = {"pack": PORTRAIT, "prepare_error": None, "frames": [b"frame-0"]}

    async def prepare(base_url: str, tenant: str, image: bytes) -> str:
        if state.get("prepare_errors"):
            raise state["prepare_errors"].pop(0)
        if state["prepare_error"]:
            raise state["prepare_error"]
        assert image == b"portrait bytes"
        return "latent-key"

    async def open_link(base_url: str, **kwargs: Any) -> FakeLink:
        if state.get("open_delay"):
            await asyncio.sleep(state["open_delay"])
        link = FakeLink(kwargs["on_frame"])
        opened.append({**kwargs, "link": link})

        async def first_frame() -> None:
            await asyncio.sleep(0.05)
            for frame in state["frames"]:
                await link.on_frame(frame)

        asyncio.get_running_loop().create_task(first_frame())
        return link

    monkeypatch.setattr(avatar_websocket, "portrait_url", lambda: "http://portrait.test")
    monkeypatch.setattr(avatar_websocket, "_load_session", lambda factory, session_id: SimpleNamespace(id=session_id))
    monkeypatch.setattr(avatar_websocket, "resolve_live_call_runtime",
                        lambda session: SimpleNamespace(avatar_pack=state["pack"],
                                                        speech_style=SimpleNamespace(emotion="sad")))
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
    (lambda monkeypatch, state: state.update(prepare_error=PortraitUnavailable("model_busy", "short")), "model_busy"),
])
def test_a_call_whose_portrait_cannot_serve_is_told_why(monkeypatch, portrait, setup, code: str) -> None:
    setup(monkeypatch, portrait.state)
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token)) as avatar:
            reply = avatar.receive_json()
    assert reply["type"] == "unavailable" and reply["code"] == code


def test_a_portrait_loading_on_demand_says_so_then_attaches_once_ready(monkeypatch, portrait) -> None:
    # The model loads when a call first asks for it; a restarting service is briefly unreachable.
    monkeypatch.setattr(avatar_websocket, "LOAD_POLL_SECONDS", 0.01)
    portrait.state["prepare_errors"] = [PortraitUnavailable("service_unreachable", "restarting"),
                                        PortraitUnavailable("warming", "loading"),
                                        PortraitUnavailable("warming", "loading")]
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token)) as avatar:
            assert avatar.receive_json() == {"type": "loading"}
            assert avatar.receive_json()["type"] == "ready"
            assert avatar.receive_bytes() == b"frame-0"
    assert portrait.opened[0]["latent_key"] == "latent-key"


def test_a_portrait_that_does_not_load_in_time_falls_back(monkeypatch, portrait) -> None:
    monkeypatch.setattr(avatar_websocket, "LOAD_POLL_SECONDS", 0.01)
    monkeypatch.setattr(avatar_websocket, "LOAD_WAIT_SECONDS", 0.05)
    portrait.state["prepare_error"] = PortraitUnavailable("warming", "loading")
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token)) as avatar:
            assert avatar.receive_json() == {"type": "loading"}
            reply = avatar.receive_json()
    assert reply["type"] == "unavailable" and reply["code"] == "warming"
    assert portrait.opened == []


def test_a_call_that_ends_while_its_portrait_loads_never_gets_a_link(monkeypatch, portrait) -> None:
    # Review finding (2026-10-31): the link opened once loaded attached to the ended call and held the service's
    # one stream slot, since nothing would close it.
    monkeypatch.setattr(avatar_websocket, "LOAD_POLL_SECONDS", 0.05)
    portrait.state["prepare_error"] = PortraitUnavailable("warming", "loading")
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with contextlib.ExitStack() as stack:
        tts = stack.enter_context(client.websocket_connect("/api/tts/live-call/websocket?portrait=1"))
        avatar = stack.enter_context(client.websocket_connect(_avatar_url(tts.receive_json()["avatar_token"])))
        assert avatar.receive_json() == {"type": "loading"}
        tts.close()
        time.sleep(0.2)
        portrait.state["prepare_error"] = None  # the model is ready now: too late for this call
        with pytest.raises(WebSocketDisconnect):
            avatar.receive_json()
    assert portrait.opened == []


def test_a_link_that_opens_after_its_call_ended_is_closed_not_attached(monkeypatch, portrait) -> None:
    portrait.state["open_delay"] = 0.3
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with contextlib.ExitStack() as stack:
        tts = stack.enter_context(client.websocket_connect("/api/tts/live-call/websocket?portrait=1"))
        avatar = stack.enter_context(client.websocket_connect(_avatar_url(tts.receive_json()["avatar_token"])))
        time.sleep(0.05)  # the avatar route is opening its link
        tts.close()
        with pytest.raises(WebSocketDisconnect) as closed:
            avatar.receive_json()
    assert closed.value.code == 1000
    assert len(portrait.opened) == 1 and portrait.opened[0]["link"].closed


def test_while_loading_the_service_is_asked_at_its_own_pace_whatever_the_browser_sends(monkeypatch, portrait) -> None:
    monkeypatch.setattr(avatar_websocket, "LOAD_POLL_SECONDS", 0.2)
    asked: list[float] = []
    portrait.state["prepare_errors"] = [PortraitUnavailable("warming", "loading") for _ in range(2)]
    original = avatar_websocket.prepare_portrait

    async def counted(*args: Any) -> str:
        asked.append(time.monotonic())
        return await original(*args)

    monkeypatch.setattr(avatar_websocket, "prepare_portrait", counted)
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        with client.websocket_connect(_avatar_url(tts.receive_json()["avatar_token"])) as avatar:
            assert avatar.receive_json() == {"type": "loading"}
            for _ in range(50):
                avatar.send_text("{}")
            assert avatar.receive_json()["type"] == "ready"
    assert len(asked) == 3
    assert min(later - earlier for earlier, later in zip(asked, asked[1:])) >= 0.19


@pytest.mark.parametrize("ack", ['{"type":"frame_ack","segment_id":"s","offset":1e400}',
                                 '{"type":"frame_ack","segment_id":"s","offset":-5}',
                                 '{"type":"frame_ack","segment_id":"s","offset":0,"decode_ms":NaN}'])
def test_an_ack_with_a_number_that_is_not_a_count_closes_the_socket_cleanly(monkeypatch, portrait, ack: str) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        with client.websocket_connect(_avatar_url(tts.receive_json()["avatar_token"])) as avatar:
            assert avatar.receive_json()["type"] == "ready"
            avatar.receive_bytes()
            avatar.send_text(ack)
            with pytest.raises(WebSocketDisconnect) as closed:
                avatar.receive_json()
    assert closed.value.code == 1003
    assert portrait.opened[0]["link"].closed


def test_the_portrait_attaches_to_the_call_relays_frames_and_play_positions(monkeypatch, portrait) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        hello = tts.receive_json()
        with client.websocket_connect(_avatar_url(hello["avatar_token"])) as avatar:
            # The test client is not a loopback address, so it starts one level down.
            assert avatar.receive_json() == {"type": "ready", "fallback_renderer": "sprite", "level": 1}
            assert avatar.receive_bytes() == b"frame-0"
            opened = portrait.opened[0]
            assert (opened["call_key"], opened["latent_key"], opened["emotion"], opened["level"]) == (
                hello["call_key"], "latent-key", "happy", 1)
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


def test_a_backlog_of_speech_frames_steps_the_quality_down(monkeypatch, portrait) -> None:
    speech = [pack({"output_id": "turn-1", "epoch": 1, "segment_id": "seg", "offset": index * 960}, b"jpeg")
              for index in range(20)]
    idle = [pack({"output_id": "idle", "epoch": 0, "segment_id": "idle", "offset": index, "count": 40}, b"jpeg")
            for index in range(40)]
    portrait.state["frames"] = idle + speech
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        hello = tts.receive_json()
        with client.websocket_connect(_avatar_url(hello["avatar_token"])) as avatar:
            assert avatar.receive_json()["level"] == 1
            for _ in range(60):
                avatar.receive_bytes()
            # The idle loop's burst is not in flight; 20 speech frames sent and 4 received are, ack after ack.
            for _ in range(3):
                avatar.send_json({"type": "frame_ack", "segment_id": "seg", "offset": 0, "received": 4, "late": 0,
                                  "decode_ms": 4.0})
            assert avatar.receive_json() == {"type": "quality", "level": 2}
            link = portrait.opened[0]["link"]
    assert {"type": "quality", "level": 2} in link.sent
