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
from tests.support.waiting import wait_until

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
    (lambda monkeypatch, state: state.update(prepare_error=PortraitUnavailable("model_missing", "missing")),
     "model_missing"),
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


def test_too_little_memory_says_so_and_the_portrait_starts_when_memory_frees(monkeypatch, portrait) -> None:
    # Longer than any load wait: only the call's end stops this one. Then the load gets its own full wait.
    monkeypatch.setattr(avatar_websocket, "MEMORY_POLL_SECONDS", 0.01)
    monkeypatch.setattr(avatar_websocket, "LOAD_POLL_SECONDS", 0.01)
    monkeypatch.setattr(avatar_websocket, "LOAD_WAIT_SECONDS", 0.1)
    short = PortraitUnavailable("model_busy", "The portrait needs about 8 GB of host memory to load")
    portrait.state["prepare_errors"] = [short] * 20 + [PortraitUnavailable("warming", "loading")] * 2
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token)) as avatar:
            assert avatar.receive_json() == {"type": "loading", "code": "model_busy"}
            assert avatar.receive_json() == {"type": "loading"}  # memory freed: now it is loading
            assert avatar.receive_json()["type"] == "ready"
    assert portrait.opened[0]["latent_key"] == "latent-key"


def test_a_call_that_ends_while_short_of_memory_stops_asking(monkeypatch, portrait) -> None:
    monkeypatch.setattr(avatar_websocket, "MEMORY_POLL_SECONDS", 0.05)
    portrait.state["prepare_error"] = PortraitUnavailable("model_busy", "short")
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with contextlib.ExitStack() as stack:
        tts = stack.enter_context(client.websocket_connect("/api/tts/live-call/websocket?portrait=1"))
        avatar = stack.enter_context(client.websocket_connect(_avatar_url(tts.receive_json()["avatar_token"])))
        assert avatar.receive_json() == {"type": "loading", "code": "model_busy"}
        tts.close()
        with pytest.raises(WebSocketDisconnect) as closed:
            avatar.receive_json()
    assert closed.value.code == 1000 and portrait.opened == []


def test_a_refusal_for_a_browser_that_has_left_raises_nothing() -> None:
    # Seen on a live call: the refusal came after the browser had gone, and the disconnect escaped the route.
    class Gone:
        async def send_json(self, _message: dict[str, Any]) -> None:
            raise WebSocketDisconnect(code=1006)

    asyncio.run(avatar_websocket._unavailable(Gone(), "model_failed", "gone"))


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
            wait_until(lambda: any(isinstance(item, dict) and item.get("type") == "play_position" for item in link.sent),
                       bool, timeout=1, interval=0.01)
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


def test_a_guest_speaking_on_a_group_call_shows_its_own_face(monkeypatch, portrait) -> None:
    # The browser names the speaker; code finds the seat and resolves the guest's own pack, never the host's.
    asked: list[tuple[str, str]] = []
    guest_pack = PORTRAIT.model_copy(update={"character_id": "bea", "portrait_emotion": "surprise"})

    def speaker_session(session: Any, speaker_id: str) -> Any:
        asked.append((session.id, speaker_id))
        return SimpleNamespace(id=session.id, speaker=speaker_id) if speaker_id == "bea" else None

    def runtime(session: Any) -> Any:
        pack = guest_pack if getattr(session, "speaker", None) == "bea" else PORTRAIT
        return SimpleNamespace(avatar_pack=pack, speech_style=SimpleNamespace(emotion="neutral"))

    monkeypatch.setattr(avatar_websocket, "_speaker_session", speaker_session)
    monkeypatch.setattr(avatar_websocket, "resolve_live_call_runtime", runtime)
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token) + "&speaker_id=bea") as avatar:
            assert avatar.receive_json()["type"] == "ready"
            assert avatar.receive_bytes() == b"frame-0"
    assert asked == [("chat-1", "bea")]
    assert portrait.opened[0]["emotion"] == "surprise"


def test_a_speaker_who_is_not_on_the_call_gets_no_face(monkeypatch, portrait) -> None:
    monkeypatch.setattr(avatar_websocket, "_speaker_session", lambda session, speaker_id: None)
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        token = tts.receive_json()["avatar_token"]
        with client.websocket_connect(_avatar_url(token) + "&speaker_id=stranger") as avatar:
            reply = avatar.receive_json()
    assert reply["type"] == "unavailable" and reply["code"] == "speaker_not_on_call"
    assert portrait.opened == []


@pytest.fixture
def idle_route(monkeypatch):
    """The idle-loop route's portrait service and members, replaced."""
    from app.platform.live_voice.portrait.link import PortraitIdleLoop
    from app.platform.live_voice.transport import portrait_idle

    state: dict[str, Any] = {"idle_error": None, "images": [], "seats": {"bea"}}
    guest_pack = PORTRAIT.model_copy(update={"character_id": "bea", "base_asset_id": "image:bea"})

    async def prepare(base_url: str, tenant: str, image: bytes) -> str:
        return f"latent:{image.decode()}"

    async def idle(base_url: str, latent_key: str) -> PortraitIdleLoop:
        if state["idle_error"]:
            raise state["idle_error"]
        return PortraitIdleLoop(80, [f"{latent_key}:idle"], [f"{latent_key}:blink"])

    def portrait_image(pack: Any, max_bytes: int) -> bytes:
        state["images"].append(pack.base_asset_id)
        return pack.base_asset_id.encode()

    def speaker_session(session: Any, speaker_id: str) -> Any:
        return SimpleNamespace(id=session.id, speaker=speaker_id) if speaker_id in state["seats"] else None

    def runtime(session: Any) -> Any:
        return SimpleNamespace(avatar_pack=guest_pack if getattr(session, "speaker", None) == "bea" else state.get(
            "host_pack", PORTRAIT))

    monkeypatch.setattr(portrait_idle, "portrait_url", lambda: "http://portrait.test")
    monkeypatch.setattr(portrait_idle, "_load_session", lambda factory, session_id: SimpleNamespace(id=session_id))
    monkeypatch.setattr(portrait_idle, "_speaker_session", speaker_session)
    monkeypatch.setattr(portrait_idle, "resolve_live_call_runtime", runtime)
    monkeypatch.setattr(portrait_idle, "default_character_avatar_service",
                        lambda: SimpleNamespace(portrait_image=portrait_image))
    monkeypatch.setattr(portrait_idle, "prepare_portrait", prepare)
    monkeypatch.setattr(portrait_idle, "idle_portrait", idle)
    return state


def test_every_member_of_a_group_call_gets_its_own_idle_loop(monkeypatch, idle_route) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())

    host = client.get("/api/tts/live-call/portrait-idle", params={"session_id": "chat-1"}).json()
    guest = client.get("/api/tts/live-call/portrait-idle", params={"session_id": "chat-1", "speaker_id": "bea"}).json()

    assert host == {"ok": True, "code": "", "message": "", "frame_ms": 80,
                    "idle": ["latent:image:maya:idle"], "blink": ["latent:image:maya:blink"]}
    assert guest["ok"] and guest["idle"] == ["latent:image:bea:idle"]
    assert idle_route["images"] == ["image:maya", "image:bea"]


def test_an_idle_loop_is_refused_for_a_stranger_a_picture_or_a_busy_service(monkeypatch, idle_route) -> None:
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())

    def code(**params: str) -> str:
        return client.get("/api/tts/live-call/portrait-idle", params={"session_id": "chat-1", **params}).json()["code"]

    assert code(speaker_id="stranger") == "speaker_not_on_call"
    idle_route["idle_error"] = PortraitUnavailable("portrait_busy", "A call is using the portrait")
    assert code(speaker_id="bea") == "portrait_busy"
    idle_route["host_pack"] = PORTRAIT.model_copy(update={"renderer": "sprite"})
    assert code() == "not_a_portrait"
    assert idle_route["images"] == ["image:bea"]


def test_a_calls_slot_is_free_before_its_portrait_closes(monkeypatch, portrait) -> None:
    # Seen on a live call (2026-11-20): on a speaker swap the browser opens the next speaker's socket at once. The
    # slot was freed only after the portrait's close, so the new socket was refused (429) and the avatar stayed off.
    from app.platform.live_voice.capacity import LiveCallCapacity
    from app.platform.live_voice.transport import websocket as tts_websocket

    capacity = LiveCallCapacity(1)
    monkeypatch.setattr(tts_websocket, "live_call_capacity", lambda: capacity)
    held_at_close: list[int] = []
    client, _logs = _configure_gateway(monkeypatch, FakeTtsProvider())
    with client.websocket_connect("/api/tts/live-call/websocket?portrait=1") as tts:
        with client.websocket_connect(_avatar_url(tts.receive_json()["avatar_token"])) as avatar:
            assert avatar.receive_json()["type"] == "ready"
            link = portrait.opened[0]["link"]

            async def close() -> None:
                held_at_close.append(int(capacity.snapshot()["active"]))
                link.closed = True

            link.close = close
            tts.close()
            wait_until(lambda: link.closed, bool, timeout=5.0, interval=0.02)
    assert held_at_close and set(held_at_close) == {0}  # the call's end and the avatar route both close it
    assert capacity.snapshot()["active"] == 0
